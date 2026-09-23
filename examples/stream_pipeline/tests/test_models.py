# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

import numpy as np

from examples.stream_pipeline.simulation.vip.behavior_model import (
    StreamBehaviorModel,
)
from examples.stream_pipeline.simulation.vip.functional_model import (
    StreamFunctionalModel,
)
from fpga_verification.sim.scoreboards import VideoPacketPolicy


def test_functional_model_returns_an_independent_equal_frame():
    frame = np.arange(12, dtype=np.uint8).reshape(3, 4)

    result = StreamFunctionalModel().process_frame(frame)

    np.testing.assert_array_equal(result, frame)
    assert result is not frame


def test_behavior_model_returns_an_exact_contract():
    frame = np.arange(12, dtype=np.uint8).reshape(3, 4)

    result = StreamBehaviorModel().process_video_frame(frame)

    assert result.policy is VideoPacketPolicy.EXACT
    np.testing.assert_array_equal(result.expected, frame)
