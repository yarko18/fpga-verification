# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Data models, test discovery, and deterministic matrix planning."""

from __future__ import annotations

import fnmatch
import hashlib
import importlib
import itertools
import json
import random
from collections import Counter
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Sequence

from .config import _MATRIX_VALUES_METADATA, ComponentConfig


class _StrategyKind(Enum):
    EXHAUSTIVE = "exhaustive"
    BALANCE = "balance"
    RANDOM = "random"


@dataclass(frozen=True)
class MatrixStrategy:
    """Validated selection rule applied after illegal configurations are removed."""

    kind: _StrategyKind
    count: int | None = None
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.kind is _StrategyKind.RANDOM:
            if self.count is None or self.count <= 0:
                raise ValueError("random matrix count must be positive")
            if self.seed is None:
                raise ValueError("random matrix seed is required")
        elif self.count is not None or self.seed is not None:
            raise ValueError(
                f"{self.kind.value} matrix strategy does not accept count or seed"
            )


def exhaustive() -> MatrixStrategy:
    """Select every legal configuration in a test's parameter space."""
    return MatrixStrategy(_StrategyKind.EXHAUSTIVE)


def balance() -> MatrixStrategy:
    """Cover every reachable value while balancing value frequencies."""
    return MatrixStrategy(_StrategyKind.BALANCE)


def random_subset(*, count: int, seed: int) -> MatrixStrategy:
    """Select a bounded reproducible sample of legal configurations."""
    return MatrixStrategy(_StrategyKind.RANDOM, count=count, seed=seed)


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
        raise TypeError(
            "parameter_matrix must decorate a cocotb test or pyuvm test class"
        )
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


class MatrixStatus(str, Enum):
    """Lifecycle and result states shared by jobs and individual test runs."""

    PENDING = "PENDING"
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP = "SKIP"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class MatrixTest:
    """One discovered simulator test and its optional matrix declaration."""

    fullname: str
    matrix: ParameterMatrix | None = None


@dataclass
class MatrixTestResult:
    """One cocotb result belonging to one matrix configuration."""

    fullname: str
    status: MatrixStatus
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
    status: MatrixStatus = MatrixStatus.PENDING
    wall_time_s: float = 0.0
    log_path: str | None = None
    error: str | None = None


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
    discovered: list[MatrixTest] = []
    seen: set[str] = set()

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
            MatrixTest(fullname=fullname, matrix=_TEST_MATRICES.get(fullname))
        )

    if not discovered:
        suffix = f" matching {', '.join(patterns)}" if patterns else ""
        raise ValueError(
            f"No cocotb/pyuvm tests discovered in {test_module!r}{suffix}"
        )
    return tuple(discovered)


def runtime_key(config: ComponentConfig) -> str:
    """Serialize a resolved configuration into its stable internal key."""
    return json.dumps(config.to_runtime_dict(), sort_keys=True, separators=(",", ":"))


def _config_id(config: ComponentConfig) -> str:
    return hashlib.sha256(runtime_key(config).encode("utf-8")).hexdigest()[:8]


def _domain(config: ComponentConfig, name: str) -> tuple:
    config_fields = {item.name: item for item in fields(config)}
    try:
        item = config_fields[name]
    except KeyError as error:
        raise ValueError(
            f"Unknown matrix field {name!r} for {type(config).__name__}"
        ) from error

    values = item.metadata.get(_MATRIX_VALUES_METADATA)
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
    legal: list[ComponentConfig] = []
    seen: set[str] = set()
    for values in itertools.product(*domains):
        candidate = dict(baseline_values)
        candidate.update(zip(vary, values))
        try:
            config = type(baseline)(**candidate)
        except ValueError:
            # __post_init__ is the configuration's legality contract. Invalid
            # candidates are planning input, not skipped or failed simulations.
            continue
        key = runtime_key(config)
        if key not in seen:
            seen.add(key)
            legal.append(config)
    return candidate_count, legal


def _value_key(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _coverage_items(
    config: ComponentConfig,
    names: tuple[str, ...],
) -> frozenset[tuple[str, str]]:
    return frozenset((name, _value_key(getattr(config, name))) for name in names)


def _balance_score(
    *,
    index: int,
    coverage: frozenset[tuple[str, str]],
    uncovered: set[tuple[str, str]],
    occurrences: Counter,
    domain_sizes: Counter,
) -> tuple[int, float, int]:
    """Prefer new values, then values used least often, then stable input order."""
    new_value_count = len(coverage & uncovered)
    imbalance_cost = sum(
        occurrences[item] / domain_sizes[item[0]] for item in coverage
    )
    return new_value_count, -imbalance_cost, -index


def _balanced_cover(
    baseline: ComponentConfig,
    configs: Sequence[ComponentConfig],
    names: tuple[str, ...],
) -> list[ComponentConfig]:
    coverage = [_coverage_items(config, names) for config in configs]
    uncovered = set().union(*coverage)
    selected: list[ComponentConfig] = []
    available = set(range(len(configs)))
    occurrences: Counter = Counter()
    domain_sizes = Counter(name for name, _ in uncovered)

    baseline_key = runtime_key(baseline)
    baseline_index = next(
        (
            index
            for index, config in enumerate(configs)
            if runtime_key(config) == baseline_key
        ),
        None,
    )
    if baseline_index is not None:
        selected.append(configs[baseline_index])
        uncovered.difference_update(coverage[baseline_index])
        occurrences.update(coverage[baseline_index])
        available.remove(baseline_index)

    while uncovered:
        best = max(
            available,
            key=lambda index: _balance_score(
                index=index,
                coverage=coverage[index],
                uncovered=uncovered,
                occurrences=occurrences,
                domain_sizes=domain_sizes,
            ),
        )
        gained = coverage[best] & uncovered
        if not gained:
            raise RuntimeError(
                "matrix coverage planner could not cover a reachable value"
            )
        selected.append(configs[best])
        uncovered.difference_update(gained)
        occurrences.update(coverage[best])
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
    if strategy.kind is _StrategyKind.EXHAUSTIVE:
        return configs
    if strategy.kind is _StrategyKind.BALANCE:
        return _balanced_cover(baseline, configs, names)
    if strategy.kind is _StrategyKind.RANDOM:
        assert strategy.count is not None
        count = min(strategy.count, len(configs))
        indexes = random.Random(strategy.seed).sample(range(len(configs)), count)
        return [configs[index] for index in indexes]
    raise AssertionError(f"Unsupported matrix strategy: {strategy.kind}")


def build_matrix_plan(
    baseline: ComponentConfig,
    tests: Sequence[MatrixTest],
) -> MatrixPlan:
    """Expand test declarations and group matching HDL configurations."""
    if not isinstance(baseline, ComponentConfig):
        raise TypeError("matrix baseline must inherit ComponentConfig")

    jobs_by_config: dict[str, MatrixJob] = {}
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
            key = runtime_key(config)
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
