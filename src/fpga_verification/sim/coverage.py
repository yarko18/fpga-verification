# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Layered functional-coverage infrastructure built on cocotb-coverage.

The runner owns files, merging and threshold enforcement. Coverage models own
only declarations and sampling. This split makes the same model work in a
single simulation and across independently compiled parameter-matrix jobs.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from typing import Any, TypeVar

from .analysis import Subscriber
from .config import _MATRIX_VALUES_METADATA, ComponentConfig


FUNCTIONAL_COVERAGE_ENV = "FPGA_VERIFICATION_FUNCTIONAL_COVERAGE"
"""Runner-provided flag enabling functional coverage inside simulator tests."""

FUNCTIONAL_COVERAGE_FILE_ENV = "FPGA_VERIFICATION_FUNCTIONAL_COVERAGE_FILE"
"""Runner-owned XML file written by the simulator process."""

FUNCTIONAL_COVERAGE_METADATA_ENV = (
    "FPGA_VERIFICATION_FUNCTIONAL_COVERAGE_METADATA"
)
"""Runner-owned JSON policy file accompanying the XML report."""

FUNCTIONAL_COVERAGE_MANAGED_ENV = (
    "FPGA_VERIFICATION_FUNCTIONAL_COVERAGE_MANAGED"
)
"""Flag moving threshold enforcement from a test to the runner."""

FUNCTIONAL_COVERAGE_DEFER_ENV = "FPGA_VERIFICATION_FUNCTIONAL_COVERAGE_DEFER"
"""Matrix-child flag deferring thresholds until all job reports are merged."""

DEFAULT_FUNCTIONAL_COVERAGE_FILE = Path("logs/functional_coverage.xml")

_ModelT = TypeVar("_ModelT")
_runtime_started = False
_sessions: dict[str, "FunctionalCoverageSession"] = {}
_models: dict[tuple[str, str], object] = {}


def functional_coverage_enabled(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether the current run requested functional coverage."""
    environ = os.environ if environ is None else environ
    return environ.get(FUNCTIONAL_COVERAGE_ENV) == "1"


def _validate_functional_coverage_runtime() -> None:
    if sys.version_info < (3, 11):
        raise RuntimeError("--coverage requires Python 3.11 or newer")
    if importlib.util.find_spec("cocotb_coverage") is None:
        raise RuntimeError(
            "--coverage requires the optional dependency; install "
            "fpga-verification[functional-coverage]"
        )


def functional_coverage_environment(
    enabled: bool,
    extra_env: Mapping[str, str] | None = None,
    *,
    artifacts_root: str | Path | None = None,
    defer: bool = False,
) -> dict[str, str] | None:
    """Validate coverage and extend the simulator environment.

    ``artifacts_root`` opts into runner-managed output. A matrix child uses
    ``defer=True`` so only the merged database is checked against thresholds.
    """
    if not enabled:
        return None if extra_env is None else dict(extra_env)
    _validate_functional_coverage_runtime()

    resolved = dict(extra_env or {})
    resolved[FUNCTIONAL_COVERAGE_ENV] = "1"
    if artifacts_root is not None:
        report = Path(artifacts_root).resolve() / DEFAULT_FUNCTIONAL_COVERAGE_FILE
        metadata = report.with_suffix(".json")
        report.unlink(missing_ok=True)
        metadata.unlink(missing_ok=True)
        resolved[FUNCTIONAL_COVERAGE_FILE_ENV] = str(report)
        resolved[FUNCTIONAL_COVERAGE_METADATA_ENV] = str(metadata)
        resolved[FUNCTIONAL_COVERAGE_MANAGED_ENV] = "1"
        if defer:
            resolved[FUNCTIONAL_COVERAGE_DEFER_ENV] = "1"
    return resolved


@dataclass(frozen=True)
class CoverageScope:
    """A stable hierarchical namespace for coverage declarations."""

    path: str

    def __post_init__(self) -> None:
        parts = self.path.split(".")
        if not self.path or any(
            not part or not part.isidentifier() for part in parts
        ):
            raise ValueError(
                "coverage scope must contain dot-separated Python identifiers"
            )

    def child(self, name: str) -> "CoverageScope":
        if not name.isidentifier():
            raise ValueError("coverage child name must be a Python identifier")
        return CoverageScope(f"{self.path}.{name}")

    def item(self, name: str) -> str:
        if not name.isidentifier():
            raise ValueError("coverage item name must be a Python identifier")
        return f"{self.path}.{name}"


class CoverageGroup(Subscriber[Any]):
    """A subscriber backed by one cocotb-coverage ``coverage_section``."""

    def __init__(self, *cover_items):
        if not cover_items:
            raise ValueError("coverage group requires at least one cover item")
        from cocotb_coverage.coverage import coverage_section

        self._sample = coverage_section(*cover_items)(self._accept)

    @staticmethod
    def _accept(_item: object) -> None:
        pass

    def write(self, item: object) -> None:
        self._sample(item)

    sample = write


def _matrix_domains(
    config: ComponentConfig,
    names: Sequence[str],
) -> dict[str, tuple[Any, ...]]:
    config_fields = {item.name: item for item in fields(config)}
    domains: dict[str, tuple[Any, ...]] = {}
    for name in names:
        try:
            item = config_fields[name]
        except KeyError as error:
            raise ValueError(
                f"Unknown coverage field {name!r} for {type(config).__name__}"
            ) from error
        values = item.metadata.get(_MATRIX_VALUES_METADATA)
        if values is None:
            raise ValueError(
                f"Coverage field {name!r} has no values; add values=... to "
                "its hdl_parameter() or matrix_parameter() declaration"
            )
        domains[name] = tuple(values)
    return domains


def _illegal_cross_bins(
    config: ComponentConfig,
    names: Sequence[str],
    domains: Mapping[str, Sequence[Any]],
) -> list[tuple[Any, ...]]:
    baseline = config.to_runtime_dict()
    ignored = []
    for values in itertools.product(*(domains[name] for name in names)):
        candidate = dict(baseline)
        candidate.update(zip(names, values))
        try:
            type(config)(**candidate)
        except ValueError:
            ignored.append(values)
    return ignored


class ParameterCoverage(CoverageGroup):
    """Cover declared matrix domains and legal configuration combinations."""

    def __init__(
        self,
        scope: CoverageScope,
        config: ComponentConfig,
        *,
        names: Sequence[str] | None = None,
        crosses: Mapping[str, Sequence[str]] | None = None,
        ignore_illegal: bool = True,
    ):
        from cocotb_coverage.coverage import CoverCross, CoverPoint

        if not isinstance(config, ComponentConfig):
            raise TypeError("parameter coverage requires a ComponentConfig")
        names = tuple(names or (item.name for item in fields(config)))
        if not names:
            raise ValueError("parameter coverage requires at least one field")
        domains = _matrix_domains(config, names)
        points = [
            CoverPoint(
                scope.item(name),
                xf=lambda sampled, field_name=name: getattr(sampled, field_name),
                bins=list(domains[name]),
            )
            for name in names
        ]
        cross_items = []
        for cross_name, cross_names_value in (crosses or {}).items():
            cross_names = tuple(cross_names_value)
            if not cross_names:
                raise ValueError(f"coverage cross {cross_name!r} is empty")
            missing = set(cross_names) - set(names)
            if missing:
                raise ValueError(
                    f"coverage cross {cross_name!r} uses unknown fields: "
                    + ", ".join(sorted(missing))
                )
            ignored = (
                _illegal_cross_bins(config, cross_names, domains)
                if ignore_illegal
                else []
            )
            cross_items.append(
                CoverCross(
                    scope.item(cross_name),
                    items=[scope.item(name) for name in cross_names],
                    ign_bins=ignored,
                )
            )
        super().__init__(*points, *cross_items)


class FunctionalCoverageSession:
    """One simulation-wide coverage lifecycle and model registry."""

    def __init__(self, root: CoverageScope):
        self.root = root

    def model(
        self,
        name: str,
        factory: Callable[[], _ModelT],
    ) -> _ModelT:
        """Create a model once and reuse it across tests in one simulator."""
        if not name.isidentifier():
            raise ValueError("coverage model name must be a Python identifier")
        key = (self.root.path, name)
        if key not in _models:
            _models[key] = factory()
        return _models[key]  # type: ignore[return-value]

    def report(
        self,
        logger: Callable[[str], object],
        *,
        requirements: Mapping[str, float] | None = None,
        minimum: float = 0.0,
        filename: str | Path | None = None,
        log_details: bool = False,
        report_bins: Sequence[str] = (),
    ) -> float:
        """Export this session; a managed runner enforces it after simulation."""
        return report_functional_coverage(
            logger,
            node=self.root.path,
            filename=filename,
            minimum=minimum,
            requirements=requirements,
            log_details=log_details,
            report_bins=report_bins,
        )


def get_functional_coverage_session(
    root: str | CoverageScope,
    environ: Mapping[str, str] | None = None,
) -> FunctionalCoverageSession | None:
    """Return the process-wide session for ``root`` when coverage is enabled."""
    if not functional_coverage_enabled(environ):
        return None
    _validate_functional_coverage_runtime()
    global _runtime_started
    if not _runtime_started:
        from cocotb_coverage.coverage import coverage_db

        coverage_db.clear()
        _runtime_started = True
    scope = root if isinstance(root, CoverageScope) else CoverageScope(root)
    if scope.path not in _sessions:
        _sessions[scope.path] = FunctionalCoverageSession(scope)
    return _sessions[scope.path]


def reset_functional_coverage() -> None:
    """Clear the process-local database and all cached coverage models."""
    from cocotb_coverage.coverage import coverage_db

    global _runtime_started
    coverage_db.clear()
    _models.clear()
    _sessions.clear()
    _runtime_started = False


def _validate_minimum(node: str, minimum: float) -> float:
    minimum = float(minimum)
    if not 0 <= minimum <= 100:
        raise ValueError(
            f"functional coverage minimum for {node!r} must be between 0 and 100"
        )
    return minimum


def _report_paths(
    filename: str | Path | None,
    environ: Mapping[str, str],
) -> tuple[Path, Path]:
    configured = environ.get(FUNCTIONAL_COVERAGE_FILE_ENV)
    if configured is not None:
        report = Path(configured)
    elif filename is not None:
        report = Path(filename)
    else:
        report = DEFAULT_FUNCTIONAL_COVERAGE_FILE
    metadata = Path(
        environ.get(
            FUNCTIONAL_COVERAGE_METADATA_ENV,
            str(report.with_suffix(".json")),
        )
    )
    return report, metadata


def _write_policy(
    path: Path,
    requirements: Mapping[str, float],
    report_bins: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "requirements": dict(requirements),
                "report_bins": list(report_bins),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_percentages(
    report: Path,
    requirements: Mapping[str, float],
) -> dict[str, float]:
    try:
        root = ET.parse(report).getroot()
    except (ET.ParseError, OSError) as error:
        raise RuntimeError(
            f"Cannot read functional coverage report {report}: {error}"
        ) from error
    nodes = {
        element.attrib.get("abs_name"): element
        for element in root.iter()
        if "abs_name" in element.attrib
    }
    percentages = {}
    for node in requirements:
        try:
            percentages[node] = float(nodes[node].attrib["cover_percentage"])
        except KeyError as error:
            raise RuntimeError(
                f"Functional coverage node {node!r} is absent from {report}"
            ) from error
    return percentages


def _check_requirements(
    report: Path,
    requirements: Mapping[str, float],
    *,
    logger: Callable[[str], object],
    enforce: bool,
) -> dict[str, float]:
    percentages = _read_percentages(report, requirements)
    failures = []
    for node, minimum in requirements.items():
        percentage = percentages[node]
        logger(
            f"Functional coverage {node}: {percentage:.1f}% "
            f"(minimum {minimum:.1f}%)"
        )
        if percentage < minimum:
            failures.append((node, percentage, minimum))
    logger(f"Functional coverage report: {report}")
    if enforce and failures:
        details = "; ".join(
            f"{node}={percentage:.1f}% < {minimum:.1f}%"
            for node, percentage, minimum in failures
        )
        raise AssertionError(f"Functional coverage requirement failed: {details}")
    return percentages


def _print_covered_bins(
    report: Path,
    nodes: Sequence[str],
    logger: Callable[[str], object],
) -> None:
    if not nodes:
        return
    from tabulate import tabulate

    root = ET.parse(report).getroot()
    elements = {
        element.attrib.get("abs_name"): element
        for element in root.iter()
        if "abs_name" in element.attrib
    }
    for node in nodes:
        try:
            element = elements[node]
        except KeyError as error:
            raise RuntimeError(
                f"Coverage bin report node {node!r} is absent from {report}"
            ) from error
        rows = [
            (child.attrib["bin"], child.attrib["hits"])
            for child in element
            if int(child.attrib.get("hits", 0)) > 0
        ]
        logger(f"Covered bins for {node}:")
        logger(
            tabulate(
                rows,
                headers=("Bin", "Hits"),
                tablefmt="rounded_outline",
                disable_numparse=True,
            )
        )


def report_functional_coverage(
    logger: Callable[[str], object],
    *,
    node: str,
    filename: str | Path | None = None,
    minimum: float = 100.0,
    requirements: Mapping[str, float] | None = None,
    environ: Mapping[str, str] | None = None,
    log_details: bool = True,
    report_bins: Sequence[str] = (),
) -> float:
    """Print and export one subtree with per-layer coverage requirements."""
    from cocotb_coverage.coverage import coverage_db

    environ = os.environ if environ is None else environ
    if node not in coverage_db:
        raise RuntimeError(f"Functional coverage node {node!r} was not sampled")
    resolved_requirements = {
        name: _validate_minimum(name, value)
        for name, value in (
            requirements if requirements is not None else {node: minimum}
        ).items()
    }
    if node not in resolved_requirements:
        resolved_requirements = {
            node: _validate_minimum(node, minimum),
            **resolved_requirements,
        }

    report, metadata = _report_paths(filename, environ)
    report.parent.mkdir(parents=True, exist_ok=True)
    if log_details:
        coverage_db.report_coverage(logger, bins=True, node=node)
    coverage_db.export_to_xml(filename=report)
    _write_policy(metadata, resolved_requirements, report_bins)
    if (
        environ.get(FUNCTIONAL_COVERAGE_MANAGED_ENV) == "1"
        and not log_details
    ):
        return float(coverage_db[node].cover_percentage)
    percentages = _check_requirements(
        report,
        resolved_requirements,
        logger=logger,
        enforce=environ.get(FUNCTIONAL_COVERAGE_MANAGED_ENV) != "1",
    )
    return percentages[node]


def finalize_functional_coverage(
    environ: Mapping[str, str],
    *,
    logger: Callable[[str], object] = print,
    enforce: bool | None = None,
) -> dict[str, float] | None:
    """Validate runner-managed output after a simulator process exits."""
    if not functional_coverage_enabled(environ):
        return None
    try:
        report = Path(environ[FUNCTIONAL_COVERAGE_FILE_ENV])
        metadata = Path(environ[FUNCTIONAL_COVERAGE_METADATA_ENV])
    except KeyError as error:
        raise RuntimeError(
            "runner-managed functional coverage has no output paths"
        ) from error
    if not report.is_file():
        raise RuntimeError(
            f"Coverage was enabled but the test did not write {report}"
        )
    if not metadata.is_file():
        raise RuntimeError(
            f"Coverage was enabled but the test did not write {metadata}"
        )
    policy = json.loads(metadata.read_text(encoding="utf-8"))
    requirements = {
        name: _validate_minimum(name, value)
        for name, value in policy["requirements"].items()
    }
    if enforce is None:
        enforce = environ.get(FUNCTIONAL_COVERAGE_DEFER_ENV) != "1"
    percentages = _check_requirements(
        report,
        requirements,
        logger=logger,
        enforce=enforce,
    )
    _print_covered_bins(report, policy.get("report_bins", ()), logger)
    return percentages


def merge_functional_coverage(
    files: Sequence[str | Path],
    output: str | Path,
    *,
    logger: Callable[[str], object] = print,
) -> dict[str, float]:
    """Merge compatible job databases and enforce their shared policy."""
    from cocotb_coverage.coverage import merge_coverage

    reports = [Path(path) for path in files]
    if not reports:
        raise ValueError("functional coverage merge requires at least one report")
    policies = []
    for report in reports:
        metadata = report.with_suffix(".json")
        if not report.is_file() or not metadata.is_file():
            raise RuntimeError(f"Incomplete functional coverage artifact: {report}")
        policies.append(json.loads(metadata.read_text(encoding="utf-8")))
    if any(policy != policies[0] for policy in policies[1:]):
        raise RuntimeError("Matrix coverage jobs declared incompatible policies")

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    merge_coverage(logger, str(output), *(str(report) for report in reports))
    metadata = output.with_suffix(".json")
    metadata.write_text(
        json.dumps(policies[0], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    environment = {
        FUNCTIONAL_COVERAGE_ENV: "1",
        FUNCTIONAL_COVERAGE_FILE_ENV: str(output),
        FUNCTIONAL_COVERAGE_METADATA_ENV: str(metadata),
    }
    return finalize_functional_coverage(
        environment,
        logger=logger,
        enforce=True,
    ) or {}
