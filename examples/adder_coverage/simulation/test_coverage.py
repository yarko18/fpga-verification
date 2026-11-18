# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge
from cocotb_coverage.coverage import coverage_db

from adder_coverage import sample_adder


@cocotb.test()
async def test_adder_functional_coverage(dut):
    """Cover operand signs and signed overflow with five directed operations."""
    dut.reset_n.value = 0
    dut.a.value = 0
    dut.b.value = 0
    clock_task = cocotb.start_soon(
        Clock(dut.clk, 10, unit="ns").start(start_high=False)
    )

    try:
        await ClockCycles(dut.clk, 2)
        dut.reset_n.value = 1

        width = len(dut.a)
        mask = (1 << width) - 1
        sign_bit = 1 << (width - 1)
        max_positive = sign_bit - 1
        cases = [
            (0, 0),                 # positive + positive, no overflow
            (max_positive, 1),      # positive + positive, overflow
            (1, sign_bit),          # positive + negative
            (mask, 1),              # negative + positive
            (sign_bit, mask),       # negative + negative, overflow
        ]

        for a, b in cases:
            await FallingEdge(dut.clk)
            dut.a.value = a
            dut.b.value = b

            await RisingEdge(dut.clk)
            await ReadOnly()

            actual_sum = int(dut.sum.value)
            actual_overflow = bool(dut.overflow.value)
            sample_adder(a, b, actual_sum, actual_overflow, width)

            expected_sum = (a + b) & mask
            expected_overflow = bool(
                ((a ^ b) & sign_bit) == 0
                and ((a ^ expected_sum) & sign_bit) != 0
            )
            assert actual_sum == expected_sum
            assert actual_overflow == expected_overflow

        coverage_db.report_coverage(dut._log.info, bins=True, node="top.adder")
        coverage_file = Path(__file__).with_name("adder_coverage.xml")
        coverage_db.export_to_xml(filename=coverage_file)
        dut._log.info("Functional coverage: %s", coverage_file)
        assert coverage_db["top.adder"].cover_percentage == 100
    finally:
        clock_task.cancel()
