# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

from dataclasses import dataclass

from fpga_verification.sim import ComponentConfig, hdl_parameter


@dataclass(frozen=True)
class TestConfig(ComponentConfig):
    """Values shared by the RTL build and the running testbench."""

    bits_per_symbol: int = hdl_parameter(8, name="BITS_PER_SYMBOL")
    symbols_per_beat: int = hdl_parameter(4, name="SYMBOLS_PER_BEAT")
    frame_width: int = 7
    frame_height: int = 3

    def __post_init__(self):
        if self.bits_per_symbol != 8:
            raise ValueError("the endianness example requires 8-bit symbols")
        if self.symbols_per_beat < 2:
            raise ValueError("symbols_per_beat must be at least 2")
        if self.frame_width <= 0 or self.frame_height <= 0:
            raise ValueError("frame dimensions must be positive")


def get_test_config():
    return TestConfig()
