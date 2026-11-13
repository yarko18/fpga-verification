# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from dataclasses import dataclass

from fpga_verification.sim import ComponentConfig, hdl_parameter


@dataclass(frozen=True)
class TestConfig(ComponentConfig):
    fifo_depth: int = hdl_parameter(16, name="FIFO_DEPTH")
    fifo_width: int = hdl_parameter(16, name="FIFO_WIDTH")

    def __post_init__(self):
        if self.fifo_depth < 2 or self.fifo_depth & (self.fifo_depth - 1):
            raise ValueError("fifo_depth must be a power of two of at least 2")
        if self.fifo_width <= 0:
            raise ValueError("fifo_width must be positive")


def get_test_config():
    return TestConfig()
