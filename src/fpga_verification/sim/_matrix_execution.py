# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Process execution and artifact handling for matrix simulations."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from ._matrix_planning import (
    MatrixJob,
    MatrixPlan,
    MatrixStatus,
    MatrixTestResult,
    plan_test_module,
    runtime_key,
)
from ._matrix_processes import ProcessRegistry, process_group_options
from ._matrix_reporting import ProgressReporter, print_plan, print_summary, write_results
from .config import CONFIG_CASE_ENV, RUNTIME_CONFIG_ENV, ComponentConfig

MATRIX_CONFIG_ENV = "FPGA_VERIFICATION_MATRIX_CONFIG_JSON"
"""Private child-process override for one resolved matrix configuration."""

MATRIX_ARTIFACT_ROOT_ENV = "FPGA_VERIFICATION_MATRIX_ARTIFACT_ROOT"
"""Private child-process root for disposable matrix artifacts."""


def resolve_matrix_config(
    config: ComponentConfig | None,
    environ: Mapping[str, str] | None = None,
) -> ComponentConfig | None:
    """Apply the private matrix child-process override when present."""
    environ = os.environ if environ is None else environ
    payload = environ.get(MATRIX_CONFIG_ENV)
    if payload is None:
        return config
    if config is None:
        raise RuntimeError(
            "matrix configuration override requires a ComponentConfig baseline"
        )
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"{MATRIX_CONFIG_ENV} must contain a JSON object") from error
    return type(config).from_runtime_dict(value)


def matrix_artifact_root(
    project_root,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return a disposable matrix root or the normal project root."""
    environ = os.environ if environ is None else environ
    return Path(environ.get(MATRIX_ARTIFACT_ROOT_ENV, project_root))


def _test_filter(names: Sequence[str]) -> str:
    return "^(?:" + "|".join(re.escape(name) for name in names) + ")$"


def _read_results(path: Path, planned_tests: Sequence[str]) -> list[MatrixTestResult]:
    planned = set(planned_tests)
    found: dict[str, MatrixTestResult] = {}
    root = ET.parse(path).getroot()
    for testcase in root.iter("testcase"):
        name = testcase.attrib.get("name")
        classname = testcase.attrib.get("classname")
        fullname = f"{classname}.{name}" if classname else name
        if fullname not in planned:
            continue
        if testcase.find("failure") is not None:
            status = MatrixStatus.FAIL
        elif testcase.find("error") is not None:
            status = MatrixStatus.ERROR
        elif testcase.find("skipped") is not None:
            status = MatrixStatus.SKIP
        else:
            status = MatrixStatus.PASS
        found[fullname] = MatrixTestResult(
            fullname=fullname,
            status=status,
            real_time_s=float(testcase.attrib.get("time", 0)),
            sim_time_ns=float(testcase.attrib.get("sim_time_ns", 0)),
            ratio_ns_s=float(testcase.attrib.get("ratio_time", 0)),
        )

    return [
        found.get(fullname, MatrixTestResult(fullname, MatrixStatus.ERROR))
        for fullname in planned_tests
    ]


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable process-level inputs shared by all matrix jobs."""

    project_root: Path
    script: Path
    simulator: str
    processes: ProcessRegistry = field(
        default_factory=ProcessRegistry,
        repr=False,
        compare=False,
    )


def _child_environment(job: MatrixJob, work_dir: Path) -> dict[str, str]:
    environment = os.environ.copy()
    serialized_config = runtime_key(job.config)
    environment[MATRIX_CONFIG_ENV] = serialized_config
    environment[MATRIX_ARTIFACT_ROOT_ENV] = str(work_dir.resolve())
    environment[RUNTIME_CONFIG_ENV] = serialized_config
    environment["COCOTB_TEST_FILTER"] = _test_filter(job.tests)
    environment["PYTHONUNBUFFERED"] = "1"
    # Matrix output is a plain-text artifact rather than interactive output.
    environment["COCOTB_ANSI_OUTPUT"] = "0"
    # The anonymous resolved config is authoritative in the child process.
    environment.pop(CONFIG_CASE_ENV, None)
    # cocotb_tools.runner changes its results filename when it detects pytest.
    environment.pop("PYTEST_CURRENT_TEST", None)
    return environment


def _error_results(job: MatrixJob) -> list[MatrixTestResult]:
    return [MatrixTestResult(fullname, MatrixStatus.ERROR) for fullname in job.tests]


def _load_job_results(job: MatrixJob, results_path: Path) -> None:
    if not results_path.is_file():
        job.results = _error_results(job)
        job.error = "Simulation did not produce results.xml"
        return
    try:
        job.results = _read_results(results_path, job.tests)
    except (ET.ParseError, ValueError) as error:
        job.results = _error_results(job)
        job.error = f"Cannot read simulator results: {error}"


def _resolve_job_status(job: MatrixJob, returncode: int) -> MatrixStatus:
    statuses = {result.status for result in job.results}
    if MatrixStatus.FAIL in statuses:
        return MatrixStatus.FAIL
    if returncode != 0 or MatrixStatus.ERROR in statuses:
        return MatrixStatus.ERROR
    if statuses == {MatrixStatus.SKIP}:
        return MatrixStatus.SKIP
    return MatrixStatus.PASS


def _preserve_or_discard_artifacts(
    job: MatrixJob,
    context: ExecutionContext,
    work_root: Path,
    work_dir: Path,
) -> None:
    if job.status in {MatrixStatus.PASS, MatrixStatus.SKIP}:
        shutil.rmtree(work_dir)
        job.log_path = None
    else:
        failure_root = context.project_root / "logs" / "matrix_failures"
        failure_root.mkdir(parents=True, exist_ok=True)
        failure_dir = failure_root / job.config_id
        if failure_dir.exists():
            shutil.rmtree(failure_dir)
        shutil.move(str(work_dir), failure_dir)
        job.log_path = (
            failure_dir / "simulation.log"
        ).relative_to(context.project_root).as_posix()

    try:
        work_root.rmdir()
    except OSError:
        # Another worker may still own a directory or may remove the shared
        # empty parent first.
        pass


def _mark_job_error(job: MatrixJob, message: str) -> None:
    if not job.results:
        job.results = _error_results(job)
    job.status = MatrixStatus.ERROR
    job.error = message


def execute_job(job: MatrixJob, context: ExecutionContext) -> None:
    """Execute one HDL configuration and all simulator tests assigned to it."""
    if context.processes.stopping:
        _mark_job_error(job, "matrix run interrupted before execution")
        return

    work_root = context.project_root / ".matrix_work"
    work_dir = work_root / job.config_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    log_path = work_dir / "simulation.log"

    process = None
    returncode = 1
    execution_error: Exception | None = None
    start = time.monotonic()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        try:
            process = subprocess.Popen(
                [sys.executable, str(context.script)],
                cwd=context.project_root,
                env=_child_environment(job, work_dir),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                **process_group_options(),
            )
            context.processes.register(process)
            returncode = process.wait()
        except Exception as error:  # subprocess and OS failures become job errors
            execution_error = error
            print(f"Matrix job failed to start: {type(error).__name__}: {error}", file=log)
            if process is not None and process.poll() is None:
                context.processes.terminate(process)
        finally:
            if process is not None and process.poll() is not None:
                context.processes.unregister(process)
    job.wall_time_s = time.monotonic() - start

    results_path = work_dir / f"sim_build_{context.simulator}" / "results.xml"
    _load_job_results(job, results_path)
    job.status = _resolve_job_status(job, returncode)

    if context.processes.stopping:
        job.error = "matrix run interrupted"
    elif execution_error is not None:
        job.error = f"matrix job execution failed: {execution_error}"
    elif returncode != 0 and job.error is None:
        job.error = f"simulation process exited with code {returncode}"

    _preserve_or_discard_artifacts(job, context, work_root, work_dir)


def _handle_worker_exception(job: MatrixJob, error: Exception) -> None:
    _mark_job_error(
        job,
        f"matrix worker failed with {type(error).__name__}: {error}",
    )


def _cancel_pending_jobs(
    plan: MatrixPlan,
    futures: Mapping[Future, MatrixJob],
) -> None:
    for future in futures:
        future.cancel()
    for job in plan.jobs:
        if job.status is MatrixStatus.PENDING:
            _mark_job_error(job, "matrix run interrupted before execution")


def _run_jobs(
    plan: MatrixPlan,
    context: ExecutionContext,
    jobs: int = 1,
) -> bool:
    """Execute jobs concurrently and report them in completion order."""
    if jobs <= 0:
        raise ValueError("matrix jobs must be positive")
    if not plan.jobs:
        return False

    worker_count = min(jobs, len(plan.jobs))
    print("Matrix execution", flush=True)
    print(f"  workers:         {worker_count}", flush=True)

    reporter = ProgressReporter(plan)
    executor = ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="fpga-matrix",
    )
    futures: dict[Future, MatrixJob] = {}
    interrupted = False
    try:
        for job in plan.jobs:
            futures[executor.submit(execute_job, job, context)] = job
        for future in as_completed(futures):
            job = futures[future]
            try:
                future.result()
            except Exception as error:
                _handle_worker_exception(job, error)
            reporter.report(job)
    except (KeyboardInterrupt, SystemExit):
        interrupted = True
        context.processes.terminate_all()
        _cancel_pending_jobs(plan, futures)
    finally:
        executor.shutdown(wait=True, cancel_futures=interrupted)
    return interrupted


def run_matrix(
    *,
    project_root,
    baseline: ComponentConfig,
    test_module: str,
    test_patterns: Sequence[str] = (),
    plan_only: bool = False,
    jobs: int = 1,
    script=None,
) -> MatrixPlan:
    """Plan and optionally execute a test module's parameter matrix."""
    project_root = Path(project_root).resolve()
    plan = plan_test_module(baseline, test_module, test_patterns)
    print_plan(plan)
    if plan_only:
        return plan

    script = Path(sys.argv[0] if script is None else script).resolve()
    if not script.is_file():
        raise FileNotFoundError(f"Cannot locate matrix runner script: {script}")
    context = ExecutionContext(
        project_root=project_root,
        script=script,
        simulator=os.getenv("SIM", "verilator"),
    )

    start = time.monotonic()
    interrupted = _run_jobs(plan, context, jobs=jobs)
    elapsed = time.monotonic() - start
    results_path = write_results(project_root, plan)
    print_summary(plan, elapsed)
    print(f"Matrix results: {results_path}", flush=True)

    failed = any(
        job.status not in {MatrixStatus.PASS, MatrixStatus.SKIP}
        for job in plan.jobs
    )
    if failed or interrupted:
        raise SystemExit(1)
    return plan
