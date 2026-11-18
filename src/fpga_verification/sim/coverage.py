# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Opt-in functional-coverage runtime helpers."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from typing import Callable, Mapping


FUNCTIONAL_COVERAGE_ENV = "FPGA_VERIFICATION_FUNCTIONAL_COVERAGE"
"""Runner-provided flag enabling functional coverage inside simulator tests."""


def functional_coverage_enabled(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether the current run requested functional coverage."""
    environ = os.environ if environ is None else environ
    return environ.get(FUNCTIONAL_COVERAGE_ENV) == "1"


def functional_coverage_environment(
    enabled: bool,
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    """Validate an enabled coverage run and extend its simulator environment."""
    if not enabled:
        return None if extra_env is None else dict(extra_env)
    if sys.version_info < (3, 11):
        raise RuntimeError("--coverage requires Python 3.11 or newer")
    if importlib.util.find_spec("cocotb_coverage") is None:
        raise RuntimeError(
            "--coverage requires the optional dependency; install "
            "fpga-verification[functional-coverage]"
        )

    resolved = dict(extra_env or {})
    resolved[FUNCTIONAL_COVERAGE_ENV] = "1"
    return resolved


def reset_functional_coverage() -> None:
    """Clear the process-local coverage database before defining a model."""
    from cocotb_coverage.coverage import coverage_db

    coverage_db.clear()


def report_functional_coverage(
    logger: Callable[[str], object],
    *,
    node: str,
    filename: str | Path,
    minimum: float = 100.0,
) -> float:
    """Print, export and enforce one functional-coverage subtree."""
    from cocotb_coverage.coverage import coverage_db

    if not 0 <= minimum <= 100:
        raise ValueError("functional coverage minimum must be between 0 and 100")
    if node not in coverage_db:
        raise RuntimeError(f"Functional coverage node {node!r} was not sampled")

    coverage_db.report_coverage(logger, bins=True, node=node)
    coverage_file = Path(filename)
    coverage_db.export_to_xml(filename=coverage_file)
    percentage = float(coverage_db[node].cover_percentage)
    logger(
        f"Functional coverage: {percentage:.1f}% "
        f"(minimum {minimum:.1f}%), report: {coverage_file}"
    )
    if percentage < minimum:
        raise AssertionError(
            f"Functional coverage {percentage:.1f}% is below {minimum:.1f}%"
        )
    return percentage
