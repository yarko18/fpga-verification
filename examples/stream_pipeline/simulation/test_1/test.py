# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

import cocotb

from ..testbench import (
    ControlPacketTest,
    UserPacketTest,
    VideoPacketTest,
)
from .config import TestConfig


@cocotb.test()
async def test_control_packet(dut):
    await ControlPacketTest(dut, TestConfig).run()


@cocotb.test()
async def test_user_packet(dut):
    await UserPacketTest(dut, TestConfig).run()


@cocotb.test()
async def test_video_packet(dut):
    await VideoPacketTest(dut, TestConfig).run()
