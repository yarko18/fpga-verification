# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
from cocotbext.avalon import AvalonSTBus
from pyuvm import uvm_env

from fpga_verification.sim.agents import VIPAgent, VIPSequence

from .behavior_model import StreamBehaviorModel
from .layout import StreamLayout
from .scoreboard import StreamScoreboard


class TestEnv(uvm_env):
    """Composition root for the video-packet endianness testbench."""

    def __init__(self, name, parent, dut, cfg):
        super().__init__(name, parent)
        self.dut = dut
        self.layout = StreamLayout.from_config(cfg)
        self.clock = None
        self.clock_task = None
        self.data_agent = None
        self.behavior_model = None
        self.scoreboard = None

    def build_phase(self):
        self.dut.reset.value = 1
        self.clock = Clock(self.dut.clk, 10, unit="ns")
        fmt = self.layout.stream_format
        self.data_agent = VIPAgent(
            "data_agent",
            self,
            clock=self.dut.clk,
            reset=self.dut.reset,
            source_bus=AvalonSTBus.from_prefix(self.dut, "din"),
            sink_bus=AvalonSTBus.from_prefix(self.dut, "dout"),
            source_fmt=fmt,
            sink_fmt=fmt,
        )
        self.behavior_model = StreamBehaviorModel(fmt.samples_per_beat)
        self.scoreboard = StreamScoreboard(
            "scoreboard",
            self,
            fmt=fmt,
            behavior_model=self.behavior_model,
            clock=self.dut.clk,
            reset=self.dut.reset,
        )

    def connect_phase(self):
        self.data_agent.source_analysis_port.connect(self.scoreboard.data_in_export)
        self.data_agent.sink_analysis_port.connect(self.scoreboard.data_out_export)

    async def run_phase(self):
        self.clock_task = cocotb.start_soon(self.clock.start(start_high=False))

    async def reset(self):
        self.dut.reset.value = 1
        await ClockCycles(self.dut.clk, 5)
        self.dut.reset.value = 0
        await ClockCycles(self.dut.clk, 2)

    async def send_packets(self, packets):
        sequence = VIPSequence.from_packets(packets, name="tutorial_packets")
        await sequence.start(self.data_agent.sequencer)

    async def drain(self):
        await self.scoreboard.drain(100, "us")

    def stop_tasks(self):
        self.data_agent.cancel_bfms()
        if self.clock_task is not None:
            self.clock_task.cancel()
            self.clock_task = None
