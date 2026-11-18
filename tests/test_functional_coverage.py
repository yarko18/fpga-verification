# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

import pytest

from fpga_verification.sim.coverage import (
    FUNCTIONAL_COVERAGE_ENV,
    functional_coverage_enabled,
    functional_coverage_environment,
)


def test_functional_coverage_enabled_reads_runner_environment():
    assert functional_coverage_enabled({FUNCTIONAL_COVERAGE_ENV: "1"})
    assert not functional_coverage_enabled({})
    assert not functional_coverage_enabled({FUNCTIONAL_COVERAGE_ENV: "0"})


def test_coverage_environment_requires_python_311(monkeypatch):
    monkeypatch.setattr("fpga_verification.sim.coverage.sys.version_info", (3, 10))

    with pytest.raises(RuntimeError, match="Python 3.11"):
        functional_coverage_environment(True)


def test_coverage_environment_requires_optional_dependency(monkeypatch):
    monkeypatch.setattr("fpga_verification.sim.coverage.sys.version_info", (3, 11))
    monkeypatch.setattr(
        "fpga_verification.sim.coverage.importlib.util.find_spec",
        lambda name: None,
    )

    with pytest.raises(RuntimeError, match="functional-coverage"):
        functional_coverage_environment(True)


def test_coverage_environment_preserves_existing_values(monkeypatch):
    monkeypatch.setattr("fpga_verification.sim.coverage.sys.version_info", (3, 11))
    monkeypatch.setattr(
        "fpga_verification.sim.coverage.importlib.util.find_spec",
        lambda name: object(),
    )

    assert functional_coverage_environment(True, {"EXISTING": "value"}) == {
        "EXISTING": "value",
        FUNCTIONAL_COVERAGE_ENV: "1",
    }
