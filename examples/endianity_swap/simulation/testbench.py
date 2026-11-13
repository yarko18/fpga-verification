# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, with_timeout
from cocotbext.avalon import (
    AvalonSTBus,
    AvalonSTFrame,
    AvalonSTSink,
    AvalonSTSource,
)

from fpga_verification.altera.video import VideoFormat, vip_packet_from_symbols


class EndianitySwapTestbench:
    """Clock, reset, and Avalon-ST transport shared by cocotb tests."""

    def __init__(self, dut, cfg):
        self.dut = dut
        self.cfg = cfg
        self.fmt = VideoFormat(
            bits_per_color=cfg.bits_per_symbol,
            pixels_in_parallel=cfg.symbols_per_beat,
        )

        self.dut.reset.value = 1
        self.clock_task = cocotb.start_soon(
            Clock(self.dut.clk, 10, unit="ns").start(start_high=False)
        )
        self.source = AvalonSTSource(
            AvalonSTBus.from_prefix(self.dut, "din"),
            self.fmt,
            self.dut.clk,
            reset=self.dut.reset,
            ready_latency=0,
            packets=True,
            idle_value=0,
        )
        self.sink = AvalonSTSink(
            AvalonSTBus.from_prefix(self.dut, "dout"),
            self.fmt,
            self.dut.clk,
            reset=self.dut.reset,
            ready_latency=0,
            packets=True,
        )

    async def reset(self):
        await ClockCycles(self.dut.clk, 5)
        self.dut.reset.value = 0
        await ClockCycles(self.dut.clk, 2)

    async def exchange(self, packet):
        await self.source.send(
            AvalonSTFrame(packet.to_symbols(self.cfg.symbols_per_beat))
        )
        frame = await with_timeout(self.sink.recv(), 10, "us")
        return vip_packet_from_symbols(
            frame.data,
            symbols_per_beat=self.cfg.symbols_per_beat,
        )

    def close(self):
        self.source.cancel()
        self.sink.cancel()
        self.clock_task.cancel()
