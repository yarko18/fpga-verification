# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

from examples.stream_pipeline.simulation.vip.behavior_model import (
    StreamBehaviorModel,
)
from examples.stream_pipeline.simulation.vip.functional_model import (
    StreamFunctionalModel,
)
from fpga_verification.sim.scoreboards import VideoPacketPolicy


def test_functional_model_reverses_each_complete_and_partial_beat():
    payload = [0x10, 0x11, 0x12, 0x13, 0x20, 0x21]

    result = StreamFunctionalModel(bytes_per_beat=4).process_payload(payload)

    assert result == [0x13, 0x12, 0x11, 0x10, 0x21, 0x20]
    assert result is not payload
    assert payload == [0x10, 0x11, 0x12, 0x13, 0x20, 0x21]


def test_behavior_model_returns_an_exact_contract():
    payload = [1, 2, 3, 4, 5]

    result = StreamBehaviorModel(bytes_per_beat=4).process_video_payload(payload)

    assert result.policy is VideoPacketPolicy.EXACT
    assert result.expected == [4, 3, 2, 1, 5]
