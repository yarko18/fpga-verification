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

from fpga_verification.altera.video import (
    VIPControlPacket,
    VIPUserPacket,
    VIPVideoPacket,
    VideoFormat,
    vip_packet_from_symbols,
)
from fpga_verification.sim import load_test_config

from .config import TestConfig

class StreamPipelineTest:
    """Common setup and lifecycle for one stream-pipeline scenario."""

    def __init__(self, dut, config_type):
        self.dut = dut
        self.cfg = load_test_config(config_type)
        self.fmt = VideoFormat(
            bits_per_color=self.cfg.bits_per_symbol,
            pixels_in_parallel=self.cfg.symbols_per_beat,
        )

        self.dut.reset.value = 1
        self.clock_task = cocotb.start_soon(
            Clock(
                self.dut.clk,
                10,
                unit="ns",
            ).start(start_high=False)
        )
        self.source = AvalonSTSource(
            AvalonSTBus.from_prefix(self.dut, "din"),
            self.fmt,
            self.dut.clk,
            reset=self.dut.reset,
            packets=True,
            idle_value=0,
        )
        self.sink = AvalonSTSink(
            AvalonSTBus.from_prefix(self.dut, "dout"),
            self.fmt,
            self.dut.clk,
            reset=self.dut.reset,
            packets=True,
        )

    async def run(self):
        try:
            await ClockCycles(self.dut.clk, 5)
            self.dut.reset.value = 0
            await ClockCycles(self.dut.clk, 2)
            await self.body()
        finally:
            self.source.cancel()
            self.sink.cancel()
            self.clock_task.cancel()

    async def body(self):
        raise NotImplementedError

    async def send_and_check(self, packet_in, expected_packet):
        await self.source.send(
            AvalonSTFrame(packet_in.to_symbols(self.cfg.symbols_per_beat))
        )
        frame = await with_timeout(self.sink.recv(), 10, "us")
        actual_packet = vip_packet_from_symbols(
            frame.data,
            symbols_per_beat=self.cfg.symbols_per_beat,
        )
        assert actual_packet == expected_packet, (
            f"received {actual_packet}, expected {expected_packet}"
        )


class ControlPacketTest(StreamPipelineTest):
    """Check that a CONTROL packet passes through unchanged."""

    async def body(self):
        packet = VIPControlPacket(self.cfg.frame_width, self.cfg.frame_height)
        await self.send_and_check(packet, packet)


class UserPacketTest(StreamPipelineTest):
    """Check that a USER packet passes through unchanged."""

    async def body(self):
        packet = VIPUserPacket(user_type=1, payload=[0x11, 0x22, 0x33])
        await self.send_and_check(packet, packet)


class VideoPacketTest(StreamPipelineTest):
    """Check that valid VIDEO symbols are reversed inside each beat."""

    async def body(self):
        packet_in = VIPVideoPacket([1, 2, 3, 4, 5])
        expected_packet = VIPVideoPacket([4, 3, 2, 1, 5])
        await self.send_and_check(packet_in, expected_packet)

@cocotb.test()
async def test_control_packet(dut):
    await ControlPacketTest(dut, TestConfig).run()


@cocotb.test()
async def test_user_packet(dut):
    await UserPacketTest(dut, TestConfig).run()


@cocotb.test()
async def test_video_packet(dut):
    await VideoPacketTest(dut, TestConfig).run()
