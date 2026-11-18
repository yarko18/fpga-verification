# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from pathlib import Path
from random import Random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge

from fpga_verification.sim import (
    exhaustive,
    functional_coverage_enabled,
    load_test_config,
    parameter_matrix,
    report_functional_coverage,
    reset_functional_coverage,
)

from .adder_coverage import create_operand_sign_coverage
from .config import TestConfig


async def _start_test(dut):
    dut.reset_n.value = 0
    dut.a.value = 0
    dut.b.value = 0
    clock_task = cocotb.start_soon(
        Clock(dut.clk, 10, unit="ns").start(start_high=False)
    )
    await ClockCycles(dut.clk, 2)
    dut.reset_n.value = 1
    return clock_task


async def _check_addition(dut, a, b, width):
    mask = (1 << width) - 1
    sign_bit = 1 << (width - 1)

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


@cocotb.test()
async def test_manual_examples(dut):
    """Check a few readable boundary and overflow examples."""
    cfg = load_test_config(TestConfig)
    sign_bit = 1 << (cfg.data_width - 1)
    mask = (1 << cfg.data_width) - 1
    cases = [
        (0, 0),
        (1, 2),
        (sign_bit - 1, 1),
        (sign_bit, mask),
        (mask, 1),
    ]
    clock_task = await _start_test(dut)
    try:
        for a, b in cases:
            await _check_addition(dut, a, b, cfg.data_width)
    finally:
        clock_task.cancel()


@parameter_matrix(vary=("data_width",), strategy=exhaustive())
@cocotb.test()
async def test_random_addition(dut):
    """Check reproducible random additions and optionally cover operand signs."""
    cfg = load_test_config(TestConfig)
    rng = Random(cfg.random_seed)
    mask = (1 << cfg.data_width) - 1

    sample_signs = None
    if functional_coverage_enabled():
        reset_functional_coverage()
        sample_signs = create_operand_sign_coverage()

    clock_task = await _start_test(dut)
    try:
        for _ in range(cfg.random_operations):
            a = rng.randrange(mask + 1)
            b = rng.randrange(mask + 1)
            await _check_addition(dut, a, b, cfg.data_width)
            if sample_signs is not None:
                sample_signs(a, b, cfg.data_width)

        if sample_signs is not None:
            report_functional_coverage(
                dut._log.info,
                node="top.adder_signs",
                filename=Path(__file__).with_name("adder_coverage.xml"),
                minimum=cfg.coverage_minimum,
            )
    finally:
        clock_task.cancel()
