# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from fpga_verification.sim import ComponentConfig, hdl_parameter
from fpga_verification.sim._matrix_execution import (
    MATRIX_ARTIFACT_ROOT_ENV,
    MATRIX_CONFIG_ENV,
    ExecutionContext,
    _read_results,
    _run_jobs,
    _test_filter,
    execute_job,
    matrix_artifact_root,
    resolve_matrix_config,
)
from fpga_verification.sim._matrix_processes import ProcessRegistry
from fpga_verification.sim._matrix_planning import (
    MatrixJob,
    MatrixPlan,
    MatrixStatus,
    MatrixTest,
    MatrixTestResult,
)


@dataclass(frozen=True)
class _Config(ComponentConfig):
    width: int = hdl_parameter(8, name="WIDTH")


def _context(tmp_path):
    script = tmp_path / "run_test.py"
    script.write_text("# fake runner\n", encoding="utf-8")
    return ExecutionContext(tmp_path, script, "verilator")


class _FakeProcess:
    pid = 12345

    def __init__(self, returncode=0):
        self._planned_returncode = returncode
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = self._planned_returncode
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def _pass_job(job):
    job.status = MatrixStatus.PASS
    job.results = [
        MatrixTestResult(name, MatrixStatus.PASS)
        for name in job.tests
    ]


def _plan(job_count):
    jobs = tuple(
        MatrixJob(
            _Config(width=index + 1),
            [f"matrix_tests.test_{index}"],
            f"{index:08d}",
        )
        for index in range(job_count)
    )
    return MatrixPlan(
        jobs=jobs,
        tests=tuple(MatrixTest(job.tests[0]) for job in jobs),
        candidates=job_count,
        legal=job_count,
        selected=job_count,
    )


def test_cocotb_filter_matches_only_planned_fullnames():
    expression = _test_filter(
        ["vip.test_pyuvm.ControlPacketTest", "vip.test_pyuvm.UserPacketTest"]
    )

    assert re.search(expression, "vip.test_pyuvm.ControlPacketTest")
    assert re.search(expression, "vip.test_pyuvm.UserPacketTest")
    assert not re.search(expression, "other.ControlPacketTest")


def test_matrix_child_override_is_strictly_restored():
    selected = _Config(width=16)
    restored = resolve_matrix_config(
        _Config(),
        {MATRIX_CONFIG_ENV: json.dumps(selected.to_runtime_dict())},
    )

    assert restored == selected


def test_matrix_artifact_root_defaults_to_project_and_accepts_child_override():
    assert matrix_artifact_root("project", {}) == matrix_artifact_root("project")
    assert matrix_artifact_root(
        "project",
        {MATRIX_ARTIFACT_ROOT_ENV: "work/config"},
    ).as_posix() == "work/config"


def test_xml_results_restore_full_names_and_missing_tests_are_errors(tmp_path):
    results = tmp_path / "results.xml"
    results.write_text(
        """<testsuites><testsuite>"""
        """<testcase classname="vip" name="pass_test" time="0.1" />"""
        """<testcase classname="vip" name="skip_test"><skipped /></testcase>"""
        """</testsuite></testsuites>""",
        encoding="utf-8",
    )

    parsed = _read_results(
        results,
        ["vip.pass_test", "vip.skip_test", "vip.missing_test"],
    )

    assert [result.status for result in parsed] == [
        MatrixStatus.PASS,
        MatrixStatus.SKIP,
        MatrixStatus.ERROR,
    ]


def test_successful_matrix_job_discards_log_and_build(monkeypatch, tmp_path):
    job = MatrixJob(_Config(), ["matrix_tests.test_smoke"], "12345678")

    def fake_subprocess_popen(command, *, env, **kwargs):
        assert "PYTEST_CURRENT_TEST" not in env
        assert env["COCOTB_ANSI_OUTPUT"] == "0"
        assert env["COCOTB_TEST_FILTER"] == "^(?:matrix_tests\\.test_smoke)$"
        artifact_root = Path(env[MATRIX_ARTIFACT_ROOT_ENV])
        build_dir = artifact_root / "sim_build_verilator"
        build_dir.mkdir(parents=True)
        (build_dir / "results.xml").write_text(
            """<testsuites><testsuite><testcase name="test_smoke" """
            """classname="matrix_tests" time="0.1" sim_time_ns="10" """
            """ratio_time="100" /></testsuite></testsuites>""",
            encoding="utf-8",
        )
        return _FakeProcess(returncode=0)

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "parent.py::test_job (call)")
    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.subprocess.Popen",
        fake_subprocess_popen,
    )
    execute_job(job, _context(tmp_path))

    assert job.status is MatrixStatus.PASS
    assert job.log_path is None
    assert not (tmp_path / ".matrix_work").exists()


def test_failed_matrix_job_preserves_log_and_config_build(monkeypatch, tmp_path):
    job = MatrixJob(_Config(), ["matrix_tests.test_smoke"], "12345678")
    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(returncode=2),
    )

    execute_job(job, _context(tmp_path))

    failure = tmp_path / "logs" / "matrix_failures" / job.config_id
    assert job.status is MatrixStatus.ERROR
    assert job.log_path == "logs/matrix_failures/12345678/simulation.log"
    assert (failure / "simulation.log").is_file()


def test_worker_pool_runs_matrix_jobs_concurrently(monkeypatch, tmp_path):
    plan = _plan(3)
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active = 0
    maximum_active = 0

    def fake_execute(job, context):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            if job in plan.jobs[:2]:
                barrier.wait(timeout=1.0)
            _pass_job(job)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.execute_job",
        fake_execute,
    )

    assert not _run_jobs(plan, _context(tmp_path), jobs=2)
    assert maximum_active == 2
    assert all(job.status is MatrixStatus.PASS for job in plan.jobs)


def test_worker_pool_reports_effective_worker_count(monkeypatch, tmp_path, capsys):
    plan = _plan(2)

    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.execute_job",
        lambda job, context: _pass_job(job),
    )

    assert not _run_jobs(plan, _context(tmp_path), jobs=8)
    assert "Matrix execution\n  workers:         2\n" in capsys.readouterr().out


def test_worker_failure_does_not_stop_remaining_jobs(monkeypatch, tmp_path):
    plan = _plan(3)
    completed = []

    def fake_execute(job, context):
        completed.append(job.config_id)
        if job is plan.jobs[0]:
            raise RuntimeError("worker failure")
        _pass_job(job)

    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.execute_job",
        fake_execute,
    )

    assert not _run_jobs(plan, _context(tmp_path), jobs=2)
    assert set(completed) == {job.config_id for job in plan.jobs}
    assert plan.jobs[0].status is MatrixStatus.ERROR
    assert all(job.status is MatrixStatus.PASS for job in plan.jobs[1:])


def test_progress_follows_worker_completion_order(monkeypatch, tmp_path):
    plan = _plan(3)
    reported = []

    def fake_execute(job, context):
        _pass_job(job)

    def reverse_completion_order(futures):
        return iter(reversed(tuple(futures)))

    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.execute_job",
        fake_execute,
    )
    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.as_completed",
        reverse_completion_order,
    )
    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.ProgressReporter.report",
        lambda self, job: reported.append(job.config_id),
    )

    assert not _run_jobs(plan, _context(tmp_path), jobs=2)
    assert reported == [job.config_id for job in reversed(plan.jobs)]


def test_ctrl_c_stops_processes_and_marks_pending_jobs_as_errors(
    monkeypatch,
    tmp_path,
):
    plan = _plan(3)
    context = _context(tmp_path)
    released = threading.Event()
    terminate_calls = []
    original_terminate_all = context.processes.terminate_all

    def fake_execute(job, current_context):
        released.wait(timeout=1.0)

    def terminate_all():
        terminate_calls.append(True)
        original_terminate_all()
        released.set()

    def interrupt_completion(futures):
        raise KeyboardInterrupt
        yield

    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.execute_job",
        fake_execute,
    )
    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.as_completed",
        interrupt_completion,
    )
    monkeypatch.setattr(context.processes, "terminate_all", terminate_all)

    assert _run_jobs(plan, context, jobs=2)
    assert terminate_calls == [True]
    assert all(job.status is MatrixStatus.ERROR for job in plan.jobs)


def test_process_registry_stops_current_and_late_processes(monkeypatch):
    registry = ProcessRegistry()
    first = object()
    second = object()
    late = object()
    terminated = []

    monkeypatch.setattr(
        "fpga_verification.sim._matrix_processes._terminate_processes",
        lambda processes: terminated.append(processes),
    )

    registry.register(first)
    registry.register(second)
    registry.terminate_all()
    registry.register(late)

    assert set(terminated[0]) == {first, second}
    assert terminated[1] == (late,)
