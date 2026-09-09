# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5
#
# Unless explicitly acquired and licensed from Licensor under another license,
# the contents of this file are subject to the Reciprocal Public License ("RPL")
# Version 1.5, or subsequent versions as allowed by the RPL, and You may not copy
# or use this file in either source code or executable form, except in compliance
# with the terms and conditions of the RPL.
#
# All software distributed under the RPL is provided strictly on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, AND LICENSOR
# HEREBY DISCLAIMS ALL SUCH WARRANTIES, INCLUDING WITHOUT LIMITATION, ANY
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, QUIET
# ENJOYMENT, OR NON-INFRINGEMENT. See the RPL for specific language governing
# rights and limitations under the RPL.

import pytest

from fpga_verification.protocols.avalon_st.intel_video import (
    IntelVIPFrameCodec,
    VIPControlPacket,
    VIPVideoPacket,
)
from fpga_verification.sim.models import BaseVIPPredictor, PacketExpectation
from fpga_verification.sim.scoreboards import BaseVIPScoreboard
from fpga_verification.video import FrameSize, ImageGenerator, VideoFormat


def _video_packet(fmt, size, value=0):
    return VIPVideoPacket([value] * fmt.frame_symbol_count(size))


def test_base_predictor_requires_tolerance_override():
    predictor = BaseVIPPredictor(
        model=object(),
        input_codec=object(),
        output_codec=object(),
    )

    with pytest.raises(NotImplementedError):
        predictor.get_tolerance()


def test_sink_format_is_required():
    try:
        BaseVIPScoreboard("no_sink_scoreboard", None, source_fmt=VideoFormat(8))
    except ValueError as exc:
        assert str(exc) == "sink_fmt must be provided"
    else:
        raise AssertionError("BaseVIPScoreboard accepted a missing sink_fmt")


def test_unexpected_control_is_fatal():
    fmt = VideoFormat(8)
    scoreboard = BaseVIPScoreboard(
        "unexpected_control_scoreboard",
        None,
        sink_fmt=fmt,
    )

    scoreboard.data_out_export.write(VIPControlPacket(4, 2))

    assert isinstance(scoreboard._failure, AssertionError)
    assert str(scoreboard._failure) == "Unexpected output CONTROL packet"
    assert scoreboard.last_output_size is None


def test_unexpected_video_is_fatal():
    fmt = VideoFormat(8)
    scoreboard = BaseVIPScoreboard(
        "unexpected_video_scoreboard",
        None,
        sink_fmt=fmt,
    )

    scoreboard.data_out_export.write(_video_packet(fmt, FrameSize(2, 2)))

    assert isinstance(scoreboard._failure, AssertionError)
    assert str(scoreboard._failure) == "Unexpected output VIDEO packet"
    assert scoreboard.output_frames_cnt == 0


def test_output_only_scoreboard_accepts_explicit_expectations():
    fmt = VideoFormat(8)
    size = FrameSize(2, 2)
    control = VIPControlPacket(size.width, size.height)
    video = _video_packet(fmt, size)
    scoreboard = BaseVIPScoreboard(
        "explicit_expectation_scoreboard",
        None,
        sink_fmt=fmt,
    )

    scoreboard.add_expectation(PacketExpectation(packet=control))
    scoreboard.add_expectation(PacketExpectation(packet=video))
    scoreboard.data_out_export.write(control)
    scoreboard.data_out_export.write(video)

    assert not scoreboard.expected_queue
    assert scoreboard.last_output_size == size
    assert scoreboard.output_frames_cnt == 1
    assert scoreboard._failure is None


def test_noncomparable_expectation_consumes_exactly_one_video():
    fmt = VideoFormat(8)
    size = FrameSize(2, 2)
    control = VIPControlPacket(size.width, size.height)
    scoreboard = BaseVIPScoreboard(
        "noncomparable_video_scoreboard",
        None,
        sink_fmt=fmt,
    )

    scoreboard.add_expectation(PacketExpectation(packet=control))
    scoreboard.add_expectation(
        PacketExpectation(compare=False, reason="corrupted frame")
    )
    scoreboard.data_out_export.write(control)
    scoreboard.data_out_export.write(_video_packet(fmt, FrameSize(1, 2)))

    assert not scoreboard.expected_queue
    assert scoreboard.output_frames_cnt == 1
    assert scoreboard._failure is None

    scoreboard.data_out_export.write(_video_packet(fmt, FrameSize(1, 2)))

    assert scoreboard.output_frames_cnt == 1
    assert isinstance(scoreboard._failure, AssertionError)
    assert str(scoreboard._failure) == "Unexpected output VIDEO packet"


def test_malformed_comparable_video_is_fatal():
    fmt = VideoFormat(8)
    size = FrameSize(2, 2)
    control = VIPControlPacket(size.width, size.height)
    video = _video_packet(fmt, size)
    scoreboard = BaseVIPScoreboard(
        "malformed_video_scoreboard",
        None,
        sink_fmt=fmt,
    )

    scoreboard.add_expectation(PacketExpectation(packet=control))
    scoreboard.add_expectation(PacketExpectation(packet=video))
    scoreboard.data_out_export.write(control)
    scoreboard.data_out_export.write(_video_packet(fmt, FrameSize(1, 2)))

    assert not scoreboard.expected_queue
    assert scoreboard.output_frames_cnt == 0
    assert isinstance(scoreboard._failure, ValueError)


def test_wrong_packet_type_does_not_consume_expectation():
    fmt = VideoFormat(8)
    size = FrameSize(2, 2)
    control = VIPControlPacket(size.width, size.height)
    video = _video_packet(fmt, size)
    scoreboard = BaseVIPScoreboard(
        "wrong_packet_type_scoreboard",
        None,
        sink_fmt=fmt,
    )

    scoreboard.add_expectation(PacketExpectation(packet=control))
    scoreboard.add_expectation(PacketExpectation(packet=video))
    scoreboard.data_out_export.write(video)

    assert len(scoreboard.expected_queue) == 2
    assert scoreboard.output_frames_cnt == 0
    assert isinstance(scoreboard._failure, AssertionError)
    assert str(scoreboard._failure) == "Unexpected output VIDEO packet"


def test_valid_video_content_mismatch_is_fatal():
    fmt = VideoFormat(8)
    size = FrameSize(2, 2)
    control = VIPControlPacket(size.width, size.height)
    expected_video = _video_packet(fmt, size, value=0)
    actual_video = _video_packet(fmt, size, value=1)
    scoreboard = BaseVIPScoreboard(
        "content_mismatch_scoreboard",
        None,
        sink_fmt=fmt,
    )

    scoreboard.add_expectation(PacketExpectation(packet=control))
    scoreboard.add_expectation(PacketExpectation(packet=expected_video))
    scoreboard.data_out_export.write(control)
    scoreboard.data_out_export.write(actual_video)

    assert scoreboard.output_frames_cnt == 0
    assert isinstance(scoreboard._failure, AssertionError)
    assert "frame mismatch" in str(scoreboard._failure)


def test_existing_predictor_flow_still_compares_input_and_output():
    fmt = VideoFormat(8)
    size = FrameSize(3, 2)
    codec = IntelVIPFrameCodec(fmt)
    frame = ImageGenerator(fmt).horizontal_ramp(size, start=1, stop=3)
    packets = codec.frame_to_packets(frame, size)
    scoreboard = BaseVIPScoreboard(
        "predictor_scoreboard",
        None,
        source_fmt=fmt,
        sink_fmt=fmt,
    )

    class PassthroughPredictor:
        def process_packet(self, packet):
            return PacketExpectation(packet=packet)

    scoreboard.predictor = PassthroughPredictor()
    for packet in packets:
        scoreboard.data_in_export.write(packet)
        scoreboard.data_out_export.write(packet)

    assert scoreboard.input_frames_cnt == 1
    assert scoreboard.output_frames_cnt == 1
    assert not scoreboard.expected_queue
    assert scoreboard._failure is None
