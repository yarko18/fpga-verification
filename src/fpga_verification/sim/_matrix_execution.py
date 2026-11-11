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
from dataclasses import dataclass
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

    if work_root.exists() and not any(work_root.iterdir()):
        work_root.rmdir()


def execute_job(job: MatrixJob, context: ExecutionContext) -> bool:
    """Execute one job and return whether an external interruption occurred."""
    work_root = context.project_root / ".matrix_work"
    work_dir = work_root / job.config_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    log_path = work_dir / "simulation.log"

    completed = None
    execution_error: Exception | None = None
    interruption: BaseException | None = None
    start = time.monotonic()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        try:
            completed = subprocess.run(
                [sys.executable, str(context.script)],
                cwd=context.project_root,
                env=_child_environment(job, work_dir),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        except (KeyboardInterrupt, SystemExit) as error:
            interruption = error
            print(f"Matrix job interrupted by {type(error).__name__}: {error}", file=log)
        except Exception as error:  # subprocess and OS failures become job errors
            execution_error = error
            print(f"Matrix job failed to start: {type(error).__name__}: {error}", file=log)
    job.wall_time_s = time.monotonic() - start

    results_path = work_dir / f"sim_build_{context.simulator}" / "results.xml"
    _load_job_results(job, results_path)
    returncode = completed.returncode if completed is not None else 1
    job.status = _resolve_job_status(job, returncode)

    if interruption is not None:
        job.error = f"matrix job interrupted by {type(interruption).__name__}"
    elif execution_error is not None:
        job.error = f"matrix job execution failed: {execution_error}"
    elif returncode != 0 and job.error is None:
        job.error = f"simulation process exited with code {returncode}"

    _preserve_or_discard_artifacts(job, context, work_root, work_dir)
    return interruption is not None


def _run_jobs(plan: MatrixPlan, context: ExecutionContext) -> bool:
    """Run jobs sequentially through a boundary suitable for a future worker pool."""
    reporter = ProgressReporter(plan)
    for job in plan.jobs:
        interrupted = execute_job(job, context)
        reporter.report(job)
        if interrupted:
            return True
    return False


def run_matrix(
    *,
    project_root,
    baseline: ComponentConfig,
    test_module: str,
    test_patterns: Sequence[str] = (),
    plan_only: bool = False,
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
    interrupted = _run_jobs(plan, context)
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
