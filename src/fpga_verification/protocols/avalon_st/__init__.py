# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Protocols transported over Avalon Streaming interfaces."""

from .coverage import (
    AVALON_ST_CYCLE_STATES,
    DEFAULT_BACKPRESSURE_BINS,
    AvalonSTCycleCoverage,
    AvalonSTCycleSample,
)

__all__ = [
    "AVALON_ST_CYCLE_STATES",
    "DEFAULT_BACKPRESSURE_BINS",
    "AvalonSTCycleCoverage",
    "AvalonSTCycleSample",
]
