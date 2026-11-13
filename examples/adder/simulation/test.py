# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from random import Random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge


@cocotb.test()
async def test_adder(dut):
    """Drive the DUT ports directly and check registered addition."""
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
        rng = Random(0xADDE)
        cases = [
            (0x00, 0x00),
            (0x12, 0x34),
            (0x7F, 0x01),
            (0x80, 0xFF),
            (0xFF, 0x01),
        ]
        cases.extend(
            (rng.randrange(mask + 1), rng.randrange(mask + 1))
            for _ in range(20)
        )

        for a, b in cases:
            await FallingEdge(dut.clk)
            dut.a.value = a
            dut.b.value = b

            await RisingEdge(dut.clk)
            await ReadOnly()

            expected_sum = (a + b) & mask
            expected_overflow = bool(
                ((a ^ b) & sign_bit) == 0
                and ((a ^ expected_sum) & sign_bit) != 0
            )
            assert int(dut.sum.value) == expected_sum
            assert int(dut.overflow.value) == expected_overflow
    finally:
        clock_task.cancel()
