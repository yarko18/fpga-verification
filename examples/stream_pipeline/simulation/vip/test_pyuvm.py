# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

import cocotb
import pyuvm
from pyuvm import uvm_test

__test__ = False

from fpga_verification.protocols.avalon_st.intel_video import (
    IntelVIPFrameCodec,
    VIPUserPacket,
)
from fpga_verification.sim import load_runtime_config
from fpga_verification.video import ImageGenerator

from .config import TestConfig
from .env import TestEnv


class BaseStreamTest(uvm_test):
    def build_phase(self):
        self.cfg = load_runtime_config(TestConfig)
        self.env = TestEnv("env", self, cocotb.top, self.cfg)

    async def run_phase(self):
        self.raise_objection()
        try:
            await self.env.reset()
            await self.body()
            await self.env.drain()
        finally:
            self.env.stop_tasks()
            self.drop_objection()

    async def body(self):
        raise NotImplementedError


@pyuvm.test()
class OrderedPacketsTest(BaseStreamTest):
    """Check control, user and video packets through one ordered pipeline."""

    async def body(self):
        layout = self.env.layout
        codec = IntelVIPFrameCodec(layout.stream_format)
        frame = ImageGenerator(
            layout.stream_format,
            default_size=layout.frame_size,
        ).horizontal_ramp()
        packets = [
            codec.control_packet(layout.frame_size),
            VIPUserPacket(user_type=1, payload=[1, 2, 3]),
            codec.frame_to_video_packet(frame, layout.frame_size),
        ]
        await self.env.send_packets(packets)
