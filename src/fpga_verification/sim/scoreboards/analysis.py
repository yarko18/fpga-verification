# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

from pyuvm import uvm_analysis_export


class AnalysisImp(uvm_analysis_export):
    """pyuvm analysis export forwarding writes to a Python callable."""

    def __init__(self, name, parent, write_fn):
        super().__init__(name, parent)
        self.write_fn = write_fn

    def write(self, item):
        self.write_fn(item)
