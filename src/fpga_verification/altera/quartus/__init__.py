# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Helpers for Quartus component generation and simulation models."""

from .simulation import prepare_intel_libraries, resolve_quartus_sim_lib

__all__ = [
    "prepare_intel_libraries",
    "resolve_quartus_sim_lib",
]
