# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Functional coverage model for the standalone adder example."""

from cocotb_coverage.coverage import CoverCross, CoverPoint


def _is_negative(value, width):
    return bool(value & (1 << (width - 1)))


@CoverPoint(
    "top.adder.a_negative",
    xf=lambda a, b, result, overflow, width: _is_negative(a, width),
    bins=[False, True],
)
@CoverPoint(
    "top.adder.b_negative",
    xf=lambda a, b, result, overflow, width: _is_negative(b, width),
    bins=[False, True],
)
@CoverPoint(
    "top.adder.overflow",
    xf=lambda a, b, result, overflow, width: overflow,
    bins=[False, True],
)
@CoverCross(
    "top.adder.operand_sign_cross",
    items=["top.adder.a_negative", "top.adder.b_negative"],
)
def sample_adder(a, b, result, overflow, width):
    """Sample one accepted and observed adder operation."""
