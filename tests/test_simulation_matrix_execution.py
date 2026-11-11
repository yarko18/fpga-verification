# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

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
from fpga_verification.sim._matrix_planning import (
    MatrixJob,
    MatrixPlan,
    MatrixStatus,
    MatrixTest,
)


@dataclass(frozen=True)
class _Config(ComponentConfig):
    width: int = hdl_parameter(8, name="WIDTH")


def _context(tmp_path):
    script = tmp_path / "run_test.py"
    script.write_text("# fake runner\n", encoding="utf-8")
    return ExecutionContext(tmp_path, script, "verilator")


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

    def fake_subprocess_run(command, *, env, **kwargs):
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
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "parent.py::test_job (call)")
    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.subprocess.run",
        fake_subprocess_run,
    )
    interrupted = execute_job(job, _context(tmp_path))

    assert not interrupted
    assert job.status is MatrixStatus.PASS
    assert job.log_path is None
    assert not (tmp_path / ".matrix_work").exists()


def test_failed_matrix_job_preserves_log_and_config_build(monkeypatch, tmp_path):
    job = MatrixJob(_Config(), ["matrix_tests.test_smoke"], "12345678")
    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2),
    )

    execute_job(job, _context(tmp_path))

    failure = tmp_path / "logs" / "matrix_failures" / job.config_id
    assert job.status is MatrixStatus.ERROR
    assert job.log_path == "logs/matrix_failures/12345678/simulation.log"
    assert (failure / "simulation.log").is_file()


def test_interruption_is_recorded_and_stops_the_sequential_orchestrator(
    monkeypatch,
    tmp_path,
):
    first = MatrixJob(_Config(), ["matrix_tests.test_a"], "11111111")
    second = MatrixJob(_Config(), ["matrix_tests.test_b"], "22222222")
    plan = MatrixPlan(
        jobs=(first, second),
        tests=(MatrixTest("matrix_tests.test_a"), MatrixTest("matrix_tests.test_b")),
        candidates=2,
        legal=2,
        selected=2,
    )
    calls = []

    def interrupt_once(*args, **kwargs):
        calls.append("called")
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "fpga_verification.sim._matrix_execution.subprocess.run",
        interrupt_once,
    )

    assert _run_jobs(plan, _context(tmp_path))
    assert calls == ["called"]
    assert first.status is MatrixStatus.ERROR
    assert second.status is MatrixStatus.PENDING
