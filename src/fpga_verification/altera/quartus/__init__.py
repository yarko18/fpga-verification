# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Quartus simulation runners and integration helpers."""

from .component import component_test_cocotb, run_component_test
from .platform_designer import platform_test_cocotb
from .rtl import rtl_test_cocotb, run_rtl_test

__all__ = [
    "component_test_cocotb",
    "platform_test_cocotb",
    "rtl_test_cocotb",
    "run_component_test",
    "run_rtl_test",
]
