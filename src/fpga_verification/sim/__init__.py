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
from .matrix import (
    balance,
    exhaustive,
    parameter_matrix,
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
    "parameter_matrix",
    "resolve_config_case",
]
