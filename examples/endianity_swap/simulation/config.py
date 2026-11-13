# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from dataclasses import dataclass

from fpga_verification.sim import ComponentConfig, hdl_parameter


@dataclass(frozen=True)
class TestConfig(ComponentConfig):
    """Independent parameters shared by the RTL and reference model."""

    bits_per_symbol: int = hdl_parameter(
        8,
        name="BITS_PER_SYMBOL",
        values=(4, 8, 12, 16),
    )
    symbols_per_beat: int = hdl_parameter(
        3,
        name="SYMBOLS_PER_BEAT",
        values=(2, 3, 4),
    )

    def __post_init__(self):
        if not 4 <= self.bits_per_symbol <= 32:
            raise ValueError("bits_per_symbol must be between 4 and 32")
        if self.symbols_per_beat < 2:
            raise ValueError("symbols_per_beat must be at least 2")


def get_test_config():
    return TestConfig()
