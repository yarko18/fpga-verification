# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from dataclasses import dataclass

from fpga_verification.sim import ComponentConfig, hdl_parameter, resolve_config_case


@dataclass(frozen=True)
class TestConfig(ComponentConfig):
    """RTL, random-test and functional-coverage parameters."""

    data_width: int = hdl_parameter(
        8,
        name="DATA_WIDTH",
        values=(4, 8, 16),
    )
    random_seed: int = 0xADDE
    random_operations: int = 20
    coverage_minimum: int = 100

    def __post_init__(self):
        if self.data_width < 2:
            raise ValueError("data_width must be at least 2")
        if self.random_operations <= 0:
            raise ValueError("random_operations must be positive")
        if not 0 <= self.coverage_minimum <= 100:
            raise ValueError("coverage_minimum must be between 0 and 100")


def get_test_config(case=None):
    return resolve_config_case(
        {
            "default": TestConfig(),
            "small": TestConfig(data_width=4),
        },
        case,
    )
