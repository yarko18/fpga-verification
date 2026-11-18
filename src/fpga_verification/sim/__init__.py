# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Simulation helpers for FPGA verification."""

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
    FUNCTIONAL_COVERAGE_ENV,
    functional_coverage_enabled,
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
    "CONFIG_CASE_ENV",
    "ComponentConfig",
    "FUNCTIONAL_COVERAGE_ENV",
    "PacketMetrics",
    "PacketObservation",
    "PacketSequenceMetrics",
    "RUNTIME_CONFIG_ENV",
    "StreamPerformanceAnalyzer",
    "hdl_parameter",
    "load_test_config",
    "matrix_parameter",
    "balance",
    "exhaustive",
    "functional_coverage_enabled",
    "parameter_matrix",
    "random_subset",
    "report_functional_coverage",
    "reset_functional_coverage",
    "resolve_config_case",
]
