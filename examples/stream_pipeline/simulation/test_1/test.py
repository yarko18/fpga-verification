# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, with_timeout
from cocotbext.avalon import (
    AvalonSTBus,
    AvalonSTFrame,
    AvalonSTSink,
    AvalonSTSource,
)

from fpga_verification.protocols.avalon_st.intel_video import (
    VIPControlPacket,
    VIPUserPacket,
    VIPVideoPacket,
    vip_packet_from_symbols,
)
from fpga_verification.sim import load_runtime_config
from fpga_verification.video import VideoFormat

from .config import TestConfig


CLOCK_PERIOD_NS = 10


@cocotb.test()
async def test_stream_pipeline(dut):
    cfg = load_runtime_config(TestConfig)
    fmt = VideoFormat(
        bits_per_color=cfg.bits_per_symbol,
        pixels_in_parallel=cfg.symbols_per_beat,
    )

    dut.reset.value = 1
    clock_task = cocotb.start_soon(
        Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns").start(start_high=False)
    )
    source = AvalonSTSource(
        AvalonSTBus.from_prefix(dut, "din"),
        fmt,
        dut.clk,
        reset=dut.reset,
        packets=True,
        idle_value=0,
    )
    sink = AvalonSTSink(
        AvalonSTBus.from_prefix(dut, "dout"),
        fmt,
        dut.clk,
        reset=dut.reset,
        packets=True,
    )

    try:
        await ClockCycles(dut.clk, 5)
        dut.reset.value = 0
        await ClockCycles(dut.clk, 2)

        control_packet = VIPControlPacket(cfg.frame_width, cfg.frame_height)
        user_packet = VIPUserPacket(user_type=1, payload=[0x11, 0x22, 0x33])
        input_packets = [
            control_packet,
            user_packet,
            VIPVideoPacket([1, 2, 3, 4, 5]),
        ]
        expected_packets = [
            control_packet,
            user_packet,
            VIPVideoPacket([4, 3, 2, 1, 5]),
        ]

        for packet in input_packets:
            await source.send(
                AvalonSTFrame(packet.to_symbols(cfg.symbols_per_beat))
            )

        for expected in expected_packets:
            frame = await with_timeout(sink.recv(), 10, "us")
            actual = vip_packet_from_symbols(
                frame.data,
                symbols_per_beat=cfg.symbols_per_beat,
            )
            assert actual == expected, f"received {actual}, expected {expected}"
    finally:
        source.cancel()
        sink.cancel()
        clock_task.cancel()
