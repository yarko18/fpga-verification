# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from dataclasses import dataclass
import importlib.util
import xml.etree.ElementTree as ET

import pytest

from fpga_verification.sim import AnalysisPort, CallbackSubscriber
from fpga_verification.sim import ComponentConfig, hdl_parameter
from fpga_verification.sim.coverage import (
    CoverageScope,
    FUNCTIONAL_COVERAGE_FILE_ENV,
    FUNCTIONAL_COVERAGE_ENV,
    FUNCTIONAL_COVERAGE_MANAGED_ENV,
    FUNCTIONAL_COVERAGE_METADATA_ENV,
    ParameterCoverage,
    finalize_functional_coverage,
    functional_coverage_enabled,
    functional_coverage_environment,
    merge_functional_coverage,
    report_functional_coverage,
    reset_functional_coverage,
)


_COCOTB_COVERAGE_AVAILABLE = (
    importlib.util.find_spec("cocotb_coverage") is not None
)
requires_cocotb_coverage = pytest.mark.skipif(
    not _COCOTB_COVERAGE_AVAILABLE,
    reason="requires the functional-coverage optional dependency",
)


@dataclass(frozen=True)
class _Config(ComponentConfig):
    width: int = hdl_parameter(8, values=(8, 16))
    lanes: int = hdl_parameter(1, values=(1, 2))

    def __post_init__(self):
        if self.width == 8 and self.lanes == 2:
            raise ValueError("unsupported combination")


@pytest.fixture(autouse=True)
def _clean_coverage_database():
    if not _COCOTB_COVERAGE_AVAILABLE:
        yield
        return
    reset_functional_coverage()
    yield
    reset_functional_coverage()


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


def test_plain_analysis_port_fans_out_without_pyuvm():
    first = []
    second = []
    port = AnalysisPort("transactions")
    port.connect(CallbackSubscriber(first.append))
    port.connect(CallbackSubscriber(second.append))

    port.write({"value": 3})

    assert first == [{"value": 3}]
    assert second == [{"value": 3}]
    assert port.subscriber_count == 2


@requires_cocotb_coverage
def test_parameter_coverage_uses_declared_domains_and_ignores_illegal_crosses():
    from cocotb_coverage.coverage import coverage_db

    scope = CoverageScope("top.parameters")
    coverage = ParameterCoverage(
        scope,
        _Config(),
        crosses={"configuration": ("width", "lanes")},
    )
    coverage.write(_Config(width=8, lanes=1))
    coverage.write(_Config(width=16, lanes=2))

    assert coverage_db[scope.item("width")].cover_percentage == 100
    assert coverage_db[scope.item("lanes")].cover_percentage == 100
    assert coverage_db[scope.item("configuration")].size == 3
    assert coverage_db[scope.item("configuration")].cover_percentage == pytest.approx(
        200 / 3
    )


def _managed_environment(report):
    return {
        FUNCTIONAL_COVERAGE_ENV: "1",
        FUNCTIONAL_COVERAGE_FILE_ENV: str(report),
        FUNCTIONAL_COVERAGE_METADATA_ENV: str(report.with_suffix(".json")),
        FUNCTIONAL_COVERAGE_MANAGED_ENV: "1",
    }


def _write_parameter_report(report, samples, *, report_bins=()):
    reset_functional_coverage()
    coverage = ParameterCoverage(
        CoverageScope("top.parameters"),
        _Config(),
        crosses={"configuration": ("width", "lanes")},
    )
    for sample in samples:
        coverage.write(sample)
    report_functional_coverage(
        lambda _message: None,
        node="top.parameters",
        minimum=0,
        environ=_managed_environment(report),
        report_bins=report_bins,
    )


@requires_cocotb_coverage
def test_managed_report_is_checked_after_simulation(tmp_path):
    report = tmp_path / "coverage.xml"
    _write_parameter_report(report, [_Config()])

    percentages = finalize_functional_coverage(
        _managed_environment(report),
        logger=lambda _message: None,
    )

    assert percentages == {"top.parameters": pytest.approx(42.86)}


@requires_cocotb_coverage
def test_matrix_reports_merge_hits_from_random_parameter_jobs(tmp_path):
    first = tmp_path / "first.xml"
    second = tmp_path / "second.xml"
    merged = tmp_path / "merged.xml"
    _write_parameter_report(first, [_Config(width=8, lanes=1)])
    _write_parameter_report(second, [_Config(width=16, lanes=2)])

    merge_functional_coverage(
        [first, second],
        merged,
        logger=lambda _message: None,
    )

    nodes = {
        node.attrib["abs_name"]: node
        for node in ET.parse(merged).getroot().iter()
    }
    assert float(nodes["top.parameters.width"].attrib["cover_percentage"]) == 100
    assert float(nodes["top.parameters.lanes"].attrib["cover_percentage"]) == 100
    assert float(
        nodes["top.parameters.configuration"].attrib["cover_percentage"]
    ) == pytest.approx(66.67)


@requires_cocotb_coverage
def test_runner_prints_only_hit_bins_requested_by_the_model(tmp_path):
    report = tmp_path / "coverage.xml"
    _write_parameter_report(
        report,
        [_Config(width=16, lanes=2)],
        report_bins=("top.parameters.configuration",),
    )
    messages = []

    finalize_functional_coverage(
        _managed_environment(report),
        logger=messages.append,
    )

    output = "\n".join(messages)
    assert "Covered bins for top.parameters.configuration" in output
    assert "(16, 2)" in output
    assert "(8, 1)" not in output
