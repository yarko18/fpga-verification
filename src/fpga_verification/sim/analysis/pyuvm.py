# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Adapter from pyuvm analysis exports to Python write callbacks."""

from pyuvm import uvm_analysis_export


class AnalysisImp(uvm_analysis_export):
    """pyuvm analysis export forwarding writes to a Python callable."""

    def __init__(self, name, parent, write_fn):
        super().__init__(name, parent)
        self.write_fn = write_fn

    def write(self, item):
        self.write_fn(item)
