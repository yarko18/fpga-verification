# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest

from fpga_verification.protocols.avalon_st.intel_video import (
    IntelVIPFrameCodec,
    VIPControlPacket,
    VIPUserPacket,
    VIPVideoPacket,
    vip_packet_from_symbols,
)
from fpga_verification.video import FrameSize, ImageGenerator, VideoFormat


@pytest.mark.parametrize("symbols_per_beat", [1, 2, 3, 4])
def test_control_packet_uses_separate_identifier_beat(symbols_per_beat):
    packet = VIPControlPacket(width=1920, height=1080)
    symbols = packet.to_symbols(symbols_per_beat)

    assert symbols[:symbols_per_beat] == [
        0xF,
        *([0] * (symbols_per_beat - 1)),
    ]
    assert len(symbols) % symbols_per_beat == 0

    decoded = VIPControlPacket.from_symbols(symbols, symbols_per_beat)
    assert decoded.width == 1920
    assert decoded.height == 1080
    assert decoded.interlacing == packet.interlacing


def test_user_and_video_packet_padding():
    user_symbols = VIPUserPacket(2, [1, 2, 3, 4]).to_symbols(3)
    video_symbols = VIPVideoPacket([5, 6, 7, 8]).to_symbols(3)

    assert user_symbols == [2, 0, 0, 1, 2, 3, 4, 0, 0]
    assert video_symbols == [0, 0, 0, 5, 6, 7, 8, 0, 0]
    assert vip_packet_from_symbols(user_symbols, 3).payload == [
        1, 2, 3, 4, 0, 0,
    ]
    assert vip_packet_from_symbols(video_symbols, 3).payload == [
        5, 6, 7, 8, 0, 0,
    ]


@pytest.mark.parametrize(
    "fmt,size",
    [
        (VideoFormat(8), FrameSize(5, 3)),
        (VideoFormat(10, 3, True, 2), FrameSize(5, 3)),
        (VideoFormat(10, 3, False, 2), FrameSize(5, 3)),
    ],
)
def test_vip_frame_packet_stream_round_trip(fmt, size):
    frame = ImageGenerator(fmt, rng=7).random(size)
    codec = IntelVIPFrameCodec(fmt)
    packet_symbols = codec.frame_to_packet_symbols(
        frame,
        size,
        user_packets=[VIPUserPacket(1, [1, 2, 3])],
    )

    assert np.array_equal(
        codec.packet_symbols_to_frame(packet_symbols, size),
        frame,
    )


def test_video_decode_uses_explicit_size_not_control_packet():
    fmt = VideoFormat(8)
    size = FrameSize(4, 2)
    frame = ImageGenerator(fmt).constant(size, 1)
    codec = IntelVIPFrameCodec(fmt)
    video_packet = codec.frame_to_video_packet(frame, size)
    wrong_control = VIPControlPacket(99, 77)

    decoded = codec.packets_to_frame(
        [wrong_control, VIPUserPacket(1, [3]), video_packet],
        size,
    )
    assert np.array_equal(decoded, frame)

    with pytest.raises(ValueError, match="resolution mismatch"):
        codec.validate_control_packet(wrong_control, size)


def test_adapters_are_stateless_and_packet_roles_are_explicit():
    fmt = VideoFormat(8, pixels_in_parallel=2)
    codec = IntelVIPFrameCodec(fmt)
    first_size = FrameSize(3, 2)
    second_size = FrameSize(7, 4)
    generator = ImageGenerator(fmt, rng=4)

    for size in (first_size, second_size):
        frame = generator.random(size)
        control = codec.control_packet(size)
        video = codec.frame_to_video_packet(frame, size)
        assert codec.validate_control_packet(control, size)
        assert np.array_equal(codec.video_packet_to_frame(video, size), frame)

    assert not hasattr(codec, "push")
    assert not hasattr(codec, "reset")


def test_packets_to_frame_requires_exactly_one_video_packet():
    fmt = VideoFormat(8)
    size = FrameSize(2, 2)
    codec = IntelVIPFrameCodec(fmt)
    frame = ImageGenerator(fmt).constant(size, 1)
    video = codec.frame_to_video_packet(frame, size)

    with pytest.raises(ValueError, match="exactly one"):
        codec.packets_to_frame([], size)
    with pytest.raises(ValueError, match="exactly one"):
        codec.packets_to_frame([video, video], size)


def test_identifier_and_control_padding_are_strict():
    with pytest.raises(ValueError, match="identifier beat padding"):
        VIPControlPacket.from_symbols([0xF, 1, 0, 0, 0, 1, 0, 0, 1, 2], 2)

    packet = VIPControlPacket(1, 1).to_symbols(2)
    packet[-1] = 1
    with pytest.raises(ValueError, match="Control packet padding"):
        VIPControlPacket.from_symbols(packet, 2)
