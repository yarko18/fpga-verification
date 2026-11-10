# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from .component import run_component_test
from .rtl import run_rtl_test

__all__ = [
    "run_component_test",
    "run_rtl_test",
]
