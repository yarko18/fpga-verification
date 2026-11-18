# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Simulation helpers for FPGA verification."""

from .analysis import AnalysisPort, CallbackSubscriber, Subscriber

from .config import (
    CONFIG_CASE_ENV,
    ComponentConfig,
    RUNTIME_CONFIG_ENV,
    hdl_parameter,
    load_test_config,
    matrix_parameter,
    resolve_config_case,
)
from .coverage import (
    CoverageGroup,
    CoverageScope,
    FUNCTIONAL_COVERAGE_ENV,
    FunctionalCoverageSession,
    ParameterCoverage,
    functional_coverage_enabled,
    get_functional_coverage_session,
    report_functional_coverage,
    reset_functional_coverage,
)
from .matrix import (
    balance,
    exhaustive,
    parameter_matrix,
    random_subset,
)
from .stream_metrics import (
    PacketMetrics,
    PacketObservation,
    PacketSequenceMetrics,
    StreamPerformanceAnalyzer,
)

__all__ = [
    "AnalysisPort",
    "CallbackSubscriber",
    "CONFIG_CASE_ENV",
    "ComponentConfig",
    "CoverageGroup",
    "CoverageScope",
    "FUNCTIONAL_COVERAGE_ENV",
    "FunctionalCoverageSession",
    "PacketMetrics",
    "PacketObservation",
    "PacketSequenceMetrics",
    "ParameterCoverage",
    "RUNTIME_CONFIG_ENV",
    "StreamPerformanceAnalyzer",
    "Subscriber",
    "hdl_parameter",
    "load_test_config",
    "matrix_parameter",
    "balance",
    "exhaustive",
    "functional_coverage_enabled",
    "get_functional_coverage_session",
    "parameter_matrix",
    "random_subset",
    "report_functional_coverage",
    "reset_functional_coverage",
    "resolve_config_case",
]
