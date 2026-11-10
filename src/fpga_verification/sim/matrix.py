# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Parameterized cocotb/pyuvm simulation planning and execution."""

from __future__ import annotations

import fnmatch
import hashlib
import importlib
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .config import (
    CONFIG_CASE_ENV,
    MATRIX_VALUES_METADATA,
    ComponentConfig,
    RUNTIME_CONFIG_ENV,
)


MATRIX_CONFIG_ENV = "FPGA_VERIFICATION_MATRIX_CONFIG_JSON"
"""Private child-process override for one resolved matrix configuration."""

MATRIX_ARTIFACT_ROOT_ENV = "FPGA_VERIFICATION_MATRIX_ARTIFACT_ROOT"
"""Private child-process root for disposable matrix artifacts."""


@dataclass(frozen=True)
class MatrixStrategy:
    """Selection rule applied after invalid configurations are removed."""

    name: str
    count: int | None = None
    seed: int | None = None


def exhaustive() -> MatrixStrategy:
    """Select every legal configuration in a test's parameter space."""
    return MatrixStrategy("exhaustive")


def balance() -> MatrixStrategy:
    """Cover every reachable value while balancing value frequencies."""
    return MatrixStrategy("balance")


def random_subset(*, count: int, seed: int) -> MatrixStrategy:
    """Select a bounded reproducible sample of legal configurations."""
    if count <= 0:
        raise ValueError("random matrix count must be positive")
    return MatrixStrategy("random", count=count, seed=seed)


@dataclass(frozen=True)
class ParameterMatrix:
    """Matrix metadata attached to one cocotb or pyuvm test."""

    vary: tuple[str, ...]
    strategy: MatrixStrategy


_TEST_MATRICES: dict[str, ParameterMatrix] = {}


def _test_identity(test) -> str:
    fullname = getattr(test, "fullname", None)
    if fullname:
        return fullname
    function = getattr(test, "func", None)
    module = getattr(test, "__module__", None)
    name = getattr(test, "__name__", None)
    if function is not None:
        module = getattr(function, "__module__", module)
        name = getattr(test, "name", None) or getattr(function, "__name__", name)
    if not module or not name:
        raise TypeError("parameter_matrix must decorate a cocotb test or pyuvm test class")
    return f"{module}.{name}"


def parameter_matrix(*, vary: Sequence[str], strategy: MatrixStrategy):
    """Declare which configuration fields one test varies.

    Place this decorator immediately above ``@cocotb.test()`` or
    ``@pyuvm.test()``. It records host-side planning metadata and returns the
    test unchanged, so an ordinary single-configuration simulation behaves as
    before.
    """
    vary = tuple(vary)
    if not vary:
        raise ValueError("parameter_matrix vary must contain at least one field")
    if len(set(vary)) != len(vary):
        raise ValueError("parameter_matrix vary fields must be unique")
    if not isinstance(strategy, MatrixStrategy):
        raise TypeError("parameter_matrix strategy must be a MatrixStrategy")

    def decorate(test):
        identity = _test_identity(test)
        _TEST_MATRICES[identity] = ParameterMatrix(vary, strategy)
        return test

    return decorate


@dataclass(frozen=True)
class MatrixTest:
    """One discovered simulator test and its optional matrix declaration."""

    fullname: str
    matrix: ParameterMatrix | None = None


@dataclass
class MatrixTestResult:
    """One cocotb result belonging to one matrix configuration."""

    fullname: str
    status: str
    real_time_s: float = 0.0
    sim_time_ns: float = 0.0
    ratio_ns_s: float = 0.0


@dataclass
class MatrixJob:
    """One unique HDL configuration and all tests sharing its build."""

    config: ComponentConfig
    tests: list[str]
    config_id: str
    results: list[MatrixTestResult] = field(default_factory=list)
    status: str = "PENDING"
    wall_time_s: float = 0.0
    log_path: str | None = None
    error: str | None = None
    _executor: Callable[["MatrixJob"], None] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def execute(self):
        if self._executor is None:
            raise RuntimeError("matrix job has no executor")
        self._executor(self)
        if self.status not in {"PASS", "SKIP"}:
            raise AssertionError(self.error or f"matrix configuration {self.config_id} failed")


@dataclass(frozen=True)
class MatrixPlan:
    """Expanded and grouped matrix ready for execution."""

    jobs: tuple[MatrixJob, ...]
    tests: tuple[MatrixTest, ...]
    candidates: int
    legal: int
    selected: int

    @property
    def test_executions(self) -> int:
        return sum(len(job.tests) for job in self.jobs)


def _is_cocotb_test(value) -> bool:
    value_type = type(value)
    return (
        value_type.__name__ == "Test"
        and value_type.__module__ == "cocotb._decorators"
        and isinstance(getattr(value, "name", None), str)
    )


def discover_matrix_tests(
    test_module: str,
    patterns: Sequence[str] = (),
) -> tuple[MatrixTest, ...]:
    """Import a test module and discover registered cocotb/pyuvm tests."""
    module = importlib.import_module(test_module)
    discovered = []
    seen = set()

    for value in vars(module).values():
        if not _is_cocotb_test(value):
            continue
        fullname = value.fullname
        if fullname in seen:
            continue
        display_name = fullname.rsplit(".", 1)[-1]
        if patterns and not any(
            fnmatch.fnmatchcase(fullname, pattern)
            or fnmatch.fnmatchcase(display_name, pattern)
            for pattern in patterns
        ):
            continue
        seen.add(fullname)
        discovered.append(
            MatrixTest(
                fullname=fullname,
                matrix=_TEST_MATRICES.get(fullname),
            )
        )

    if not discovered:
        suffix = f" matching {', '.join(patterns)}" if patterns else ""
        raise ValueError(f"No cocotb/pyuvm tests discovered in {test_module!r}{suffix}")
    return tuple(discovered)


def _runtime_key(config: ComponentConfig) -> str:
    return json.dumps(config.to_runtime_dict(), sort_keys=True, separators=(",", ":"))


def _config_id(config: ComponentConfig) -> str:
    return hashlib.sha256(_runtime_key(config).encode("utf-8")).hexdigest()[:8]


def _domain(config: ComponentConfig, name: str) -> tuple:
    config_fields = {item.name: item for item in fields(config)}
    try:
        item = config_fields[name]
    except KeyError as error:
        raise ValueError(
            f"Unknown matrix field {name!r} for {type(config).__name__}"
        ) from error

    values = item.metadata.get(MATRIX_VALUES_METADATA)
    if values is None:
        raise ValueError(
            f"Matrix field {name!r} has no values; add values=... to its "
            "hdl_parameter() or matrix_parameter() declaration"
        )
    return tuple(values)


def _candidate_configs(
    baseline: ComponentConfig,
    vary: tuple[str, ...],
) -> tuple[int, list[ComponentConfig]]:
    domains = [_domain(baseline, name) for name in vary]
    candidate_count = 1
    for values in domains:
        candidate_count *= len(values)

    baseline_values = baseline.to_runtime_dict()
    legal = []
    seen = set()
    for values in itertools.product(*domains):
        candidate = dict(baseline_values)
        candidate.update(zip(vary, values))
        try:
            config = type(baseline)(**candidate)
        except ValueError:
            # __post_init__ is the configuration's legality contract. Invalid
            # candidates are planning input, not skipped or failed simulations.
            continue
        key = _runtime_key(config)
        if key not in seen:
            seen.add(key)
            legal.append(config)
    return candidate_count, legal


def _value_key(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _coverage_items(config: ComponentConfig, names: tuple[str, ...]):
    return frozenset(
        (name, _value_key(getattr(config, name)))
        for name in names
    )


def _balanced_cover(
    baseline: ComponentConfig,
    configs: Sequence[ComponentConfig],
    names: tuple[str, ...],
) -> list[ComponentConfig]:
    coverage = [_coverage_items(config, names) for config in configs]
    remaining = set().union(*coverage)
    selected = []
    available = set(range(len(configs)))
    occurrences = defaultdict(int)
    domain_sizes = defaultdict(int)
    for name, _ in remaining:
        domain_sizes[name] += 1

    baseline_key = _runtime_key(baseline)
    baseline_index = next(
        (
            index
            for index, config in enumerate(configs)
            if _runtime_key(config) == baseline_key
        ),
        None,
    )
    if baseline_index is not None:
        selected.append(configs[baseline_index])
        remaining.difference_update(coverage[baseline_index])
        for item in coverage[baseline_index]:
            occurrences[item] += 1
        available.remove(baseline_index)

    while remaining:
        def score(index):
            items = coverage[index]
            imbalance_cost = sum(
                occurrences[item] / domain_sizes[item[0]]
                for item in items
            )
            return len(items & remaining), -imbalance_cost, -index

        best = max(
            available,
            key=score,
        )
        gained = coverage[best] & remaining
        if not gained:
            raise RuntimeError("matrix coverage planner could not cover a reachable value")
        selected.append(configs[best])
        remaining.difference_update(gained)
        for item in coverage[best]:
            occurrences[item] += 1
        available.remove(best)
    return selected


def _select_configs(
    baseline: ComponentConfig,
    configs: list[ComponentConfig],
    names: tuple[str, ...],
    strategy: MatrixStrategy,
) -> list[ComponentConfig]:
    if not configs:
        raise ValueError("Matrix declaration has no legal configurations")
    if strategy.name == "exhaustive":
        return configs
    if strategy.name == "balance":
        return _balanced_cover(baseline, configs, names)
    if strategy.name == "random":
        count = min(strategy.count or 0, len(configs))
        generator = random.Random(strategy.seed)
        indexes = generator.sample(range(len(configs)), count)
        return [configs[index] for index in indexes]
    raise ValueError(f"Unknown matrix strategy: {strategy.name}")


def build_matrix_plan(
    baseline: ComponentConfig,
    tests: Sequence[MatrixTest],
) -> MatrixPlan:
    """Expand test declarations and group matching HDL configurations."""
    if not isinstance(baseline, ComponentConfig):
        raise TypeError("matrix baseline must inherit ComponentConfig")

    jobs_by_config: OrderedDict[str, MatrixJob] = OrderedDict()
    candidate_total = 0
    legal_total = 0
    selected_total = 0

    for test in tests:
        if test.matrix is None:
            candidate_count = 1
            legal_configs = [baseline]
            selected_configs = legal_configs
        else:
            candidate_count, legal_configs = _candidate_configs(
                baseline,
                test.matrix.vary,
            )
            selected_configs = _select_configs(
                baseline,
                legal_configs,
                test.matrix.vary,
                test.matrix.strategy,
            )

        candidate_total += candidate_count
        legal_total += len(legal_configs)
        selected_total += len(selected_configs)

        for config in selected_configs:
            key = _runtime_key(config)
            job = jobs_by_config.get(key)
            if job is None:
                job = MatrixJob(config, [], _config_id(config))
                jobs_by_config[key] = job
            if test.fullname not in job.tests:
                job.tests.append(test.fullname)

    return MatrixPlan(
        jobs=tuple(jobs_by_config.values()),
        tests=tuple(tests),
        candidates=candidate_total,
        legal=legal_total,
        selected=selected_total,
    )


def plan_test_module(
    baseline: ComponentConfig,
    test_module: str,
    patterns: Sequence[str] = (),
) -> MatrixPlan:
    """Discover one module and build its grouped matrix plan."""
    return build_matrix_plan(
        baseline,
        discover_matrix_tests(test_module, patterns),
    )


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
        raise RuntimeError("matrix configuration override requires a ComponentConfig baseline")
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
    found = {}
    root = ET.parse(path).getroot()
    for testcase in root.iter("testcase"):
        name = testcase.attrib.get("name")
        classname = testcase.attrib.get("classname")
        fullname = f"{classname}.{name}" if classname else name
        if fullname not in planned:
            continue
        if testcase.find("failure") is not None:
            status = "FAIL"
        elif testcase.find("error") is not None:
            status = "ERROR"
        elif testcase.find("skipped") is not None:
            status = "SKIP"
        else:
            status = "PASS"
        found[fullname] = MatrixTestResult(
            fullname=fullname,
            status=status,
            real_time_s=float(testcase.attrib.get("time", 0)),
            sim_time_ns=float(testcase.attrib.get("sim_time_ns", 0)),
            ratio_ns_s=float(testcase.attrib.get("ratio_time", 0)),
        )

    return [
        found.get(fullname, MatrixTestResult(fullname, "ERROR"))
        for fullname in planned_tests
    ]


@dataclass(frozen=True)
class _ExecutionContext:
    project_root: Path
    script: Path
    simulator: str


def _execute_job(job: MatrixJob, context: _ExecutionContext) -> None:
    work_root = context.project_root / ".matrix_work"
    work_dir = work_root / job.config_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    log_path = work_dir / "simulation.log"

    environment = os.environ.copy()
    environment[MATRIX_CONFIG_ENV] = _runtime_key(job.config)
    environment[MATRIX_ARTIFACT_ROOT_ENV] = str(work_dir.resolve())
    environment[RUNTIME_CONFIG_ENV] = _runtime_key(job.config)
    environment["COCOTB_TEST_FILTER"] = _test_filter(job.tests)
    environment["PYTHONUNBUFFERED"] = "1"
    # The full anonymous config is authoritative. A host-side preset selected
    # for the parent may no longer exist in a child or may construct unrelated
    # state before the runner can apply the matrix override.
    environment.pop(CONFIG_CASE_ENV, None)
    # Pytest is only the parent-side matrix orchestrator. If this variable
    # reaches cocotb_tools.runner in the child process, the runner assumes the
    # simulation itself is a pytest test and renames results.xml.
    environment.pop("PYTEST_CURRENT_TEST", None)

    start = time.monotonic()
    execution_error = None
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        try:
            completed = subprocess.run(
                [sys.executable, str(context.script)],
                cwd=context.project_root,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        except BaseException as error:
            execution_error = error
            completed = None
            print(f"Matrix job interrupted by {type(error).__name__}: {error}", file=log)
    job.wall_time_s = time.monotonic() - start

    results_path = work_dir / f"sim_build_{context.simulator}" / "results.xml"
    if results_path.is_file():
        try:
            job.results = _read_results(results_path, job.tests)
        except (ET.ParseError, ValueError) as error:
            job.results = [
                MatrixTestResult(fullname, "ERROR")
                for fullname in job.tests
            ]
            job.error = f"Cannot read simulator results: {error}"
    else:
        job.results = [
            MatrixTestResult(fullname, "ERROR")
            for fullname in job.tests
        ]
        job.error = "Simulation did not produce results.xml"

    result_statuses = {result.status for result in job.results}
    returncode = completed.returncode if completed is not None else 1
    if returncode != 0 or "ERROR" in result_statuses:
        job.status = "ERROR" if "FAIL" not in result_statuses else "FAIL"
    elif "FAIL" in result_statuses:
        job.status = "FAIL"
    elif result_statuses == {"SKIP"}:
        job.status = "SKIP"
    else:
        job.status = "PASS"

    if execution_error is not None:
        job.error = f"matrix job interrupted by {type(execution_error).__name__}"
    elif returncode != 0 and job.error is None:
        job.error = f"simulation process exited with code {returncode}"

    if job.status in {"PASS", "SKIP"}:
        shutil.rmtree(work_dir)
        job.log_path = None
    else:
        failure_root = context.project_root / "logs" / "matrix_failures"
        failure_root.mkdir(parents=True, exist_ok=True)
        failure_dir = failure_root / job.config_id
        if failure_dir.exists():
            shutil.rmtree(failure_dir)
        shutil.move(str(work_dir), failure_dir)
        job.log_path = str((failure_dir / "simulation.log").relative_to(context.project_root))

    if work_root.exists() and not any(work_root.iterdir()):
        work_root.rmdir()
    if execution_error is not None:
        raise execution_error


class _ProgressReporter:
    def __init__(self, plan: MatrixPlan):
        self.plan = plan
        self.completed_configs = 0
        self.completed_runs = 0

    def report(self, job: MatrixJob, terminal=None):
        self.completed_configs += 1
        self.completed_runs += len(job.tests)
        line = (
            f"[configs {self.completed_configs}/{len(self.plan.jobs)} | "
            f"runs {self.completed_runs}/{self.plan.test_executions}] "
            f"{job.config_id} {job.status:<5} "
            f"{sum(result.status == 'PASS' for result in job.results)}/"
            f"{len(job.tests)} runs {job.wall_time_s:.2f}s"
        )
        if terminal is None:
            print(line, flush=True)
        else:
            terminal.write_line(line)


def _run_with_pytest(plan: MatrixPlan) -> int:
    import pytest

    reporter = _ProgressReporter(plan)

    class MatrixPlugin:
        terminal = None

        def pytest_configure(self, config):
            self.terminal = config.pluginmanager.get_plugin("terminalreporter")

        def pytest_generate_tests(self, metafunc):
            if "matrix_job" in metafunc.fixturenames:
                metafunc.parametrize(
                    "matrix_job",
                    plan.jobs,
                    ids=[job.config_id for job in plan.jobs],
                )

        @pytest.hookimpl(hookwrapper=True)
        def pytest_runtest_makereport(self, item, call):
            outcome = yield
            report = outcome.get_result()
            if report.when != "call" or not hasattr(item, "callspec"):
                return
            job = item.callspec.params.get("matrix_job")
            if job is not None:
                reporter.report(job, self.terminal)

        def pytest_report_teststatus(self, report, config):
            if "matrix_job" in report.nodeid:
                if report.when == "call":
                    return report.outcome, "", ""
                return "", "", ""
            return None

    with tempfile.TemporaryDirectory(prefix="fpga_verification_matrix_") as directory:
        pytest_file = Path(directory) / "test_matrix_jobs.py"
        pytest_file.write_text(
            "def test_matrix_job(matrix_job):\n"
            "    matrix_job.execute()\n",
            encoding="utf-8",
        )
        return int(
            pytest.main(
                [
                    "-q",
                    "--tb=no",
                    "--no-summary",
                    "--disable-warnings",
                    "-p",
                    "no:cacheprovider",
                    str(pytest_file),
                ],
                plugins=[MatrixPlugin()],
            )
        )


def _print_plan(plan: MatrixPlan) -> None:
    print("Matrix plan", flush=True)
    print(f"  candidate runs: {plan.candidates}", flush=True)
    print(f"  legal runs:     {plan.legal}", flush=True)
    print(f"  selected runs:  {plan.selected}", flush=True)
    print(f"  configs:        {len(plan.jobs)}", flush=True)
    print(f"  test cases:     {len(plan.tests)}", flush=True)


def _result_summary(plan: MatrixPlan):
    by_test = defaultdict(lambda: defaultdict(int))
    real_time = defaultdict(float)
    sim_time = defaultdict(float)
    for job in plan.jobs:
        for result in job.results:
            by_test[result.fullname][result.status] += 1
            real_time[result.fullname] += result.real_time_s
            sim_time[result.fullname] += result.sim_time_ns
    return by_test, real_time, sim_time


def _print_summary(plan: MatrixPlan, elapsed: float) -> None:
    by_test, real_time, sim_time = _result_summary(plan)
    names = [test.fullname for test in plan.tests]
    name_width = max([len("TEST")] + [len(name) for name in names])
    separator = "*" * (name_width + 75)
    print(separator)
    print(
        f"** {'TEST':<{name_width}}  PASS  FAIL  ERROR  SKIP  TOTAL  "
        f"SIM TIME (ns)  REAL TIME (s) **"
    )
    print(separator)
    for name in names:
        counts = by_test[name]
        total = sum(counts.values())
        print(
            f"** {name:<{name_width}}  {counts['PASS']:>4}  {counts['FAIL']:>4}  "
            f"{counts['ERROR']:>5}  {counts['SKIP']:>4}  {total:>5}  "
            f"{sim_time[name]:>13.2f}  {real_time[name]:>13.2f} **"
        )
    print(separator)
    config_counts = defaultdict(int)
    for job in plan.jobs:
        config_counts[job.status] += 1
    print(
        f"** CONFIGS={len(plan.jobs)} PASS={config_counts['PASS']} "
        f"FAIL={config_counts['FAIL']} ERROR={config_counts['ERROR']} "
        f"SKIP={config_counts['SKIP']} RUNS={plan.test_executions} "
        f"TOTAL TIME={elapsed:.2f}s **"
    )
    print(separator)

    failed = [job for job in plan.jobs if job.status not in {"PASS", "SKIP"}]
    if failed:
        print("\nFailed matrix configurations:")
        for job in failed:
            failed_tests = ", ".join(
                result.fullname
                for result in job.results
                if result.status in {"FAIL", "ERROR"}
            )
            print(f"  {job.config_id}: {failed_tests or ', '.join(job.tests)}")
            for name, value in job.config.to_runtime_dict().items():
                print(f"    {name}={value}")
            if job.log_path:
                print(f"    log: {job.log_path}")


def _write_results(project_root: Path, plan: MatrixPlan, elapsed: float) -> Path:
    configurations = []
    for job in plan.jobs:
        configurations.append(
            {
                "id": job.config_id,
                "config": job.config.to_runtime_dict(),
                "status": job.status,
                "wall_time_s": job.wall_time_s,
                "log": job.log_path,
                "tests": [
                    {
                        "fullname": result.fullname,
                        "status": result.status,
                        "real_time_s": result.real_time_s,
                        "sim_time_ns": result.sim_time_ns,
                        "ratio_ns_s": result.ratio_ns_s,
                    }
                    for result in job.results
                ],
            }
        )

    path = project_root / "logs" / "matrix-results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "elapsed_s": elapsed,
                "candidates": plan.candidates,
                "legal": plan.legal,
                "selected": plan.selected,
                "tests": [
                    {
                        "fullname": test.fullname,
                        "vary": list(test.matrix.vary) if test.matrix else [],
                        "strategy": (
                            {
                                "name": test.matrix.strategy.name,
                                "count": test.matrix.strategy.count,
                                "seed": test.matrix.strategy.seed,
                            }
                            if test.matrix
                            else {
                                "name": "baseline",
                                "count": None,
                                "seed": None,
                            }
                        ),
                    }
                    for test in plan.tests
                ],
                "configurations": configurations,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


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
    _print_plan(plan)
    if plan_only:
        return plan

    script = Path(sys.argv[0] if script is None else script).resolve()
    if not script.is_file():
        raise FileNotFoundError(f"Cannot locate matrix runner script: {script}")
    context = _ExecutionContext(
        project_root=project_root,
        script=script,
        simulator=os.getenv("SIM", "verilator"),
    )
    for job in plan.jobs:
        job._executor = lambda current, context=context: _execute_job(current, context)

    start = time.monotonic()
    pytest_status = _run_with_pytest(plan)
    elapsed = time.monotonic() - start
    results_path = _write_results(project_root, plan, elapsed)
    _print_summary(plan, elapsed)
    print(f"Matrix results: {results_path}", flush=True)

    failed = any(job.status not in {"PASS", "SKIP"} for job in plan.jobs)
    if failed or pytest_status:
        raise SystemExit(1)
    return plan
