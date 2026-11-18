# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Functional coverage model for the standalone adder example."""


def _sign(value, width):
    return "-" if value & (1 << (width - 1)) else "+"


def create_operand_sign_coverage():
    """Declare and return a sampler for the four operand-sign combinations."""
    from cocotb_coverage.coverage import CoverCross, CoverPoint

    @CoverPoint(
        "top.adder_signs.a_sign",
        xf=lambda a, b, width: _sign(a, width),
        bins=["+", "-"],
    )
    @CoverPoint(
        "top.adder_signs.b_sign",
        xf=lambda a, b, width: _sign(b, width),
        bins=["+", "-"],
    )
    @CoverCross(
        "top.adder_signs.cross",
        items=["top.adder_signs.a_sign", "top.adder_signs.b_sign"],
    )
    def sample(a, b, width):
        """Sample one operation after its registered result was checked."""

    return sample
