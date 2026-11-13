# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from random import Random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, with_timeout
from cocotbext.avalon import (
    AvalonFormat,
    AvalonSTBus,
    AvalonSTFrame,
    AvalonSTSink,
    AvalonSTSource,
)

from fpga_verification.sim import load_test_config

from .config import TestConfig


def backpressure():
    while True:
        yield False
        yield False
        yield True


@cocotb.test()
async def test_stream_fifo(dut):
    """Check FIFO ordering while the output applies RL=0 backpressure."""
    cfg = load_test_config(TestConfig)
    fmt = AvalonFormat(bits_per_symbol=cfg.fifo_width, symbols_per_beat=1)

    dut.reset.value = 1
    clock_task = cocotb.start_soon(
        Clock(dut.clk, 10, unit="ns").start(start_high=False)
    )
    source = AvalonSTSource(
        AvalonSTBus.from_prefix(dut, "din"),
        fmt,
        dut.clk,
        reset=dut.reset,
        ready_latency=0,
        packets=False,
        idle_value=0,
    )
    sink = AvalonSTSink(
        AvalonSTBus.from_prefix(dut, "dout"),
        fmt,
        dut.clk,
        reset=dut.reset,
        ready_latency=0,
        packets=False,
    )
    sink.set_pause_generator(backpressure())

    try:
        await ClockCycles(dut.clk, 5)
        dut.reset.value = 0
        await ClockCycles(dut.clk, 2)

        rng = Random(0xF1F0)
        mask = (1 << cfg.fifo_width) - 1
        expected = [rng.randrange(mask + 1) for _ in range(64)]

        await source.send(AvalonSTFrame(expected))
        received = []
        for _ in expected:
            frame = await with_timeout(sink.recv(), 10, "us")
            received.extend(frame.data)

        await source.wait()
        assert received == expected
    finally:
        source.cancel()
        sink.cancel()
        clock_task.cancel()
