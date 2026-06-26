# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import pytest

from fpga_verification.protocols.avalon_st.intel_video import (
    VIPControlPacket,
    VIPProtocolChecker,
    VIPProtocolError,
    VIPUserPacket,
    VIPVideoPacket,
)
from fpga_verification.sim.agents import VIPItem, VIPSequence
from fpga_verification.video import FrameSize, VideoFormat


def _video_packet(fmt, size):
    symbol_count = fmt.frame_symbol_count(size)
    return VIPVideoPacket([0] * symbol_count)


def test_first_video_requires_control_packet():
    fmt = VideoFormat(8)
    checker = VIPProtocolChecker(fmt)

    checker.observe(VIPUserPacket(1, [1]))
    with pytest.raises(VIPProtocolError, match="before any control"):
        checker.observe(_video_packet(fmt, FrameSize(4, 2)))


def test_repeated_same_size_frames_use_active_control_packet():
    fmt = VideoFormat(10, 3, True, 2)
    size = FrameSize(5, 3)
    checker = VIPProtocolChecker(fmt)

    checker.observe(VIPControlPacket(size.width, size.height))
    checker.observe(_video_packet(fmt, size))
    checker.observe(VIPUserPacket(2, [7, 0, 0]))
    checker.observe(_video_packet(fmt, size))

    assert checker.control_size == size


def test_size_change_requires_new_control_packet():
    fmt = VideoFormat(8)
    first_size = FrameSize(4, 2)
    second_size = FrameSize(5, 2)
    checker = VIPProtocolChecker(fmt)

    checker.observe(VIPControlPacket(first_size.width, first_size.height))
    checker.observe(_video_packet(fmt, first_size))

    with pytest.raises(VIPProtocolError, match="new control packet"):
        checker.observe(_video_packet(fmt, second_size))

    checker.observe(VIPControlPacket(second_size.width, second_size.height))
    checker.observe(_video_packet(fmt, second_size))
    assert checker.control_size == second_size


def test_checker_uses_valid_video_payload_symbol_count():
    fmt = VideoFormat(
        bits_per_symbol=10,
        number_of_color_planes=3,
        color_planes_are_in_parallel=False,
        pixels_in_parallel=4,
    )
    size = FrameSize(5, 2)
    checker = VIPProtocolChecker(fmt)

    checker.observe(VIPControlPacket(size.width, size.height))
    assert checker.expected_video_symbols() == size.width * size.height * 3
    checker.observe(_video_packet(fmt, size))


def test_checker_reset_requires_control_again():
    fmt = VideoFormat(8)
    size = FrameSize(2, 2)
    checker = VIPProtocolChecker(fmt)
    checker.observe(VIPControlPacket(size.width, size.height))
    checker.reset()

    with pytest.raises(VIPProtocolError, match="before any control"):
        checker.observe(_video_packet(fmt, size))


def test_invalid_control_resolution_is_rejected():
    checker = VIPProtocolChecker(VideoFormat(8))
    with pytest.raises(VIPProtocolError, match="positive frame size"):
        checker.observe(VIPControlPacket(0, 2))


def test_item_and_sequence_preserve_packets():
    packets = [VIPControlPacket(2, 2), VIPVideoPacket([1, 2, 3, 4])]
    item = VIPItem.from_packet(packets[0])
    sequence = VIPSequence.from_packets(packets, name="frame")

    assert item.to_vip_packet() is packets[0]
    assert [entry.to_vip_packet() for entry in sequence.items] == packets

    with pytest.raises(TypeError, match="VIPPacket"):
        VIPItem(object())
