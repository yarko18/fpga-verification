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

import asyncio
from itertools import count

import pytest
from cocotb.types import Logic

from fpga_verification.protocols.avalon_st.intel_video import (
    VIPControlPacket,
    VIPUserPacket,
    VIPVideoPacket,
)
from fpga_verification.sim.scoreboards import (
    BaseVIPScoreboard,
    CheckMode,
    PacketExpectation,
    UserPacketPolicy,
)
from fpga_verification.sim.scoreboards import intel_video as scoreboard_module
from fpga_verification.video import FrameSize, VideoFormat


def _video_packet(fmt, size, value=0):
    return VIPVideoPacket([value] * fmt.frame_symbol_count(size))


_scoreboard_ids = count()


def _scoreboard(fmt=None, **kwargs):
    return BaseVIPScoreboard(
        f"scoreboard_{next(_scoreboard_ids)}",
        None,
        sink_fmt=fmt or VideoFormat(8),
        **kwargs,
    )


def test_sink_format_is_required():
    with pytest.raises(ValueError, match="sink_fmt must be provided"):
        BaseVIPScoreboard("no_sink_scoreboard", None, source_fmt=VideoFormat(8))


def test_default_user_packet_policy_is_drop():
    assert _scoreboard().user_packet_policy is UserPacketPolicy.DROP


def test_exact_control_comparison_rejects_wrong_geometry():
    scoreboard = _scoreboard()
    scoreboard.add_expectation(PacketExpectation(VIPControlPacket(4, 2)))

    scoreboard.data_out_export.write(VIPControlPacket(3, 2))

    assert isinstance(scoreboard._failure, AssertionError)
    assert "expected width 4" in str(scoreboard._failure)


def test_shape_control_comparison_still_checks_geometry():
    scoreboard = _scoreboard()
    control = VIPControlPacket(4, 2)
    scoreboard.add_expectation(PacketExpectation(control, check=CheckMode.SHAPE))
    scoreboard.data_out_export.write(control)

    assert not scoreboard.expected_queue
    assert scoreboard._failure is None


def test_exact_video_comparison_checks_decoded_frame_content():
    fmt = VideoFormat(8)
    size = FrameSize(2, 2)
    scoreboard = _scoreboard(fmt)
    scoreboard.add_expectation(PacketExpectation(VIPControlPacket(2, 2)))
    scoreboard.add_expectation(PacketExpectation(_video_packet(fmt, size, value=0)))
    scoreboard.data_out_export.write(VIPControlPacket(2, 2))
    scoreboard.data_out_export.write(_video_packet(fmt, size, value=1))

    assert isinstance(scoreboard._failure, AssertionError)
    assert "frame mismatch" in str(scoreboard._failure)


def test_exact_video_comparison_supports_parallel_pixels():
    fmt = VideoFormat(10, pixels_in_parallel=2)
    size = FrameSize(3, 2)
    scoreboard = _scoreboard(fmt)
    scoreboard.add_expectation(PacketExpectation(VIPControlPacket(3, 2)))
    scoreboard.add_expectation(PacketExpectation(_video_packet(fmt, size, value=7)))

    scoreboard.data_out_export.write(VIPControlPacket(3, 2))
    scoreboard.data_out_export.write(_video_packet(fmt, size, value=7))

    assert scoreboard._failure is None
    assert scoreboard.output_frames_cnt == 1


def test_shape_video_comparison_checks_payload_length_only():
    fmt = VideoFormat(8)
    size = FrameSize(2, 2)
    scoreboard = _scoreboard(fmt)
    scoreboard.add_expectation(PacketExpectation(VIPControlPacket(2, 2)))
    scoreboard.add_expectation(
        PacketExpectation(_video_packet(fmt, size), check=CheckMode.SHAPE)
    )
    scoreboard.data_out_export.write(VIPControlPacket(2, 2))
    scoreboard.data_out_export.write(_video_packet(fmt, size, value=7))

    assert not scoreboard.expected_queue
    assert scoreboard.output_frames_cnt == 1
    assert scoreboard._failure is None


def test_exact_and_shape_user_comparisons_have_explicit_contracts():
    scoreboard = _scoreboard()
    scoreboard.add_expectation(PacketExpectation(VIPUserPacket(1, [1, 2])))
    scoreboard.data_out_export.write(VIPUserPacket(1, [1, 2]))
    assert scoreboard._failure is None

    scoreboard = _scoreboard()
    scoreboard.add_expectation(
        PacketExpectation(VIPUserPacket(1, [1, 2]), check=CheckMode.SHAPE)
    )
    scoreboard.data_out_export.write(VIPUserPacket(1, [7, 8]))
    assert scoreboard._failure is None


def test_default_drop_contract_rejects_any_unexpected_user_output():
    scoreboard = _scoreboard()

    scoreboard.data_out_export.write(VIPUserPacket(1, [1]))

    assert isinstance(scoreboard._failure, AssertionError)
    assert str(scoreboard._failure) == "Unexpected output USER1 packet"


def test_wrong_packet_type_is_fatal_without_consuming_expectation():
    scoreboard = _scoreboard()
    scoreboard.add_expectation(PacketExpectation(VIPControlPacket(4, 2)))

    scoreboard.data_out_export.write(VIPVideoPacket([0]))

    assert len(scoreboard.expected_queue) == 1
    assert isinstance(scoreboard._failure, AssertionError)


def test_reset_aborts_pending_expectations_and_calls_custom_hook():
    class ResetAwareScoreboard(BaseVIPScoreboard):
        def __init__(self):
            super().__init__("reset_aware", None, sink_fmt=VideoFormat(8))
            self.reset_count = 0

        def on_reset(self):
            self.reset_count += 1

    scoreboard = ResetAwareScoreboard()
    scoreboard.add_expectation(PacketExpectation(VIPControlPacket(4, 2)))

    scoreboard.reset()

    assert not scoreboard.expected_queue
    assert scoreboard.reset_count == 1
    assert scoreboard._failure is None


def test_reset_does_not_mask_an_already_recorded_mismatch():
    scoreboard = _scoreboard()
    scoreboard.add_expectation(PacketExpectation(VIPControlPacket(4, 2)))
    scoreboard.data_out_export.write(VIPControlPacket(3, 2))

    scoreboard.reset()

    with pytest.raises(AssertionError, match="expected width 4"):
        scoreboard.check_phase()


def test_unresolved_reset_is_inactive_until_the_testbench_drives_it():
    class UnresolvedReset:
        value = Logic("Z")

    scoreboard = _scoreboard(reset=UnresolvedReset())

    assert scoreboard._reset_active() is False


def test_missing_expectation_fails_in_check_phase():
    scoreboard = _scoreboard()
    scoreboard.add_expectation(PacketExpectation(VIPControlPacket(4, 2)))

    with pytest.raises(AssertionError, match="Missing output packets"):
        scoreboard.check_phase()


def test_drain_times_out_when_an_expectation_never_arrives(monkeypatch):
    scoreboard = _scoreboard()
    scoreboard.add_expectation(PacketExpectation(VIPControlPacket(4, 2)))

    async def timeout(*args, **kwargs):
        raise scoreboard_module.SimTimeoutError()

    monkeypatch.setattr(scoreboard_module, "with_timeout", timeout)

    with pytest.raises(AssertionError, match="1 expectation.*remain"):
        asyncio.run(scoreboard.drain(1, "us"))


def test_drain_observes_the_configured_quiet_window(monkeypatch):
    scoreboard = _scoreboard(clock=object(), quiet_cycles=3)
    edges = 0

    async def rising_edge(clock):
        nonlocal edges
        edges += 1

    async def next_timestep():
        return None

    monkeypatch.setattr(scoreboard_module, "RisingEdge", rising_edge)
    monkeypatch.setattr(scoreboard_module, "NextTimeStep", next_timestep)

    asyncio.run(scoreboard.drain(1, "us"))

    assert edges == 3


def test_drain_rejects_extra_output_during_quiet_window(monkeypatch):
    scoreboard = _scoreboard(clock=object(), quiet_cycles=2)

    async def rising_edge(clock):
        scoreboard.data_out_export.write(VIPControlPacket(4, 2))

    async def next_timestep():
        return None

    monkeypatch.setattr(scoreboard_module, "RisingEdge", rising_edge)
    monkeypatch.setattr(scoreboard_module, "NextTimeStep", next_timestep)

    with pytest.raises(AssertionError, match="Unexpected output CONTROL packet"):
        asyncio.run(scoreboard.drain(1, "us"))
