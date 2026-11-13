# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

import cocotb

from fpga_verification.altera.video import VIPUserPacket, VIPVideoPacket
from fpga_verification.sim import (
    balance,
    exhaustive,
    load_test_config,
    parameter_matrix,
)

from .config import TestConfig
from .reference_model import EndianitySwapModel
from .testbench import EndianitySwapTestbench


async def run_packet_test(dut, packet_factory):
    cfg = load_test_config(TestConfig)
    model = EndianitySwapModel(cfg.symbols_per_beat)
    testbench = EndianitySwapTestbench(dut, cfg)
    try:
        await testbench.reset()
        packet = packet_factory(cfg)
        expected = model.process(packet)
        actual = await testbench.exchange(packet)
        assert actual == expected, f"received {actual}, expected {expected}"
    finally:
        testbench.close()


@parameter_matrix(
    vary=("bits_per_symbol", "symbols_per_beat"),
    strategy=balance(),
)
@cocotb.test()
async def test_user_packet(dut):
    """The model and DUT both preserve USER packet payloads."""

    def make_packet(cfg):
        length = 2 * cfg.symbols_per_beat + 1
        return VIPUserPacket(1, list(range(1, length + 1)))

    await run_packet_test(dut, make_packet)


@parameter_matrix(
    vary=("bits_per_symbol", "symbols_per_beat"),
    strategy=exhaustive(),
)
@cocotb.test()
async def test_video_packet(dut):
    """The model and DUT reverse valid symbols in every VIDEO beat."""

    def make_packet(cfg):
        length = 3 * cfg.symbols_per_beat - 1
        return VIPVideoPacket(list(range(1, length + 1)))

    await run_packet_test(dut, make_packet)
