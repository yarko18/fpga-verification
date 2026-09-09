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

from collections import deque

import logging
from cocotb.triggers import Event, SimTimeoutError, with_timeout
from pyuvm import uvm_scoreboard

from fpga_verification.video import FrameSize, compare_frames

from fpga_verification.protocols.avalon_st.intel_video import (
    IntelVIPFrameCodec,
    VIPControlPacket,
    VIPUserPacket,
    VIPVideoPacket,
)

from fpga_verification.sim.models.intel_video import PacketExpectation
from fpga_verification.sim.scoreboards.analysis import AnalysisImp


class BaseVIPScoreboard(uvm_scoreboard):
    """Match one Intel VIP output stream against ordered expectations.

    The optional input stream can feed a predictor. Expectations may instead
    be added explicitly by a test-specific subclass. Each expectation matches
    exactly one output packet.
    """

    def __init__(self, name, parent, source_fmt=None, sink_fmt=None):
        super().__init__(name, parent)

        if sink_fmt is None:
            raise ValueError("sink_fmt must be provided")

        self.data_in_export = (
            AnalysisImp("data_in_export", self, self._process_input_packet)
            if source_fmt is not None
            else None
        )
        self.data_out_export = AnalysisImp(
            "data_out_export",
            self,
            self._process_output_packet,
        )
        self.log = logging.getLogger(f"cocotb.base_vip_scoreboard.{name}")

        self.vip_input_codec = (
            IntelVIPFrameCodec(source_fmt) if source_fmt is not None else None
        )
        self.vip_output_codec = IntelVIPFrameCodec(sink_fmt)
        self.predictor = None

        self.expected_queue = deque()
        self.last_output_size = None

        self.input_frames_cnt = 0
        self.output_frames_cnt = 0
        self.waited_frames_cnt = 0

        self._failure = None
        self._frame_checked = Event()

    def add_expectation(self, expectation):
        """Queue one explicit output expectation."""
        if not isinstance(expectation, PacketExpectation):
            raise TypeError("expectation must be a PacketExpectation")

        self.expected_queue.append(expectation)

    def get_frame_count(self):
        """Return the frame counter used by wait_frame_checked()."""
        return self.output_frames_cnt

    def process_frame_done(self):
        self.output_frames_cnt += 1
        self._frame_checked.set()

    def _record_failure(self, exc):
        if self._failure is None:
            self._failure = exc
        self._frame_checked.set()

    def _process_input_packet(self, packet):
        try:
            if self.predictor is not None:
                expectation = self.predictor.process_packet(packet)

                if expectation is not None:
                    self.add_expectation(expectation)

            if isinstance(packet, VIPVideoPacket):
                self.input_frames_cnt += 1

        except Exception as exc:
            self._record_failure(exc)

    def _process_output_packet(self, packet):
        """Match one output packet against the next expectation."""
        if self._failure is not None:
            return
        try:
            if isinstance(packet, VIPControlPacket):
                self._process_control_packet(packet)

            elif isinstance(packet, VIPVideoPacket):
                self._process_video_packet(packet)

            elif isinstance(packet, VIPUserPacket):
                self._process_user_packet(packet)

            else:
                raise AssertionError(f"Unknown packet type: {packet.packet_type}")

        except Exception as exc:
            self._record_failure(exc)

    def _process_control_packet(self, packet):
        if not self.expected_queue:
            raise AssertionError("Unexpected output CONTROL packet")

        expectation = self.expected_queue[0]
        if not isinstance(expectation.packet, VIPControlPacket):
            raise AssertionError("Unexpected output CONTROL packet")

        self.expected_queue.popleft()
        self.last_output_size = FrameSize(packet.width, packet.height)

        if not expectation.compare:
            return

        packet_ref = expectation.packet
        self._compare_control_packet(packet, packet_ref)

    @staticmethod
    def _compare_control_packet(packet, packet_ref):
        assert packet_ref.width == packet.width, (
            f"expected width {packet_ref.width}, got {packet.width}"
        )
        assert packet_ref.height == packet.height, (
            f"expected height {packet_ref.height}, got {packet.height}"
        )
        assert (
            packet.interlacing.is_interlaced
            == packet_ref.interlacing.is_interlaced
        ), (
            f"expected interlacing {packet_ref.interlacing}, "
            f"got {packet.interlacing}"
        )

    def _process_video_packet(self, packet):
        if not self.expected_queue:
            raise AssertionError("Unexpected output VIDEO packet")

        expectation = self.expected_queue[0]
        if not self._is_video_expectation(expectation):
            raise AssertionError("Unexpected output VIDEO packet")

        self.expected_queue.popleft()

        if not expectation.compare:
            self.log.info("Skip frame compare: %s", expectation.reason)
            self.process_frame_done()
            return

        frame_ref = self.vip_output_codec.video_packet_to_frame(
            expectation.packet,
            self.last_output_size,
        )
        frame_out = self.vip_output_codec.video_packet_to_frame(
            packet,
            self.last_output_size,
        )

        self.log.info(f"Compare output frame with reference")

        compare_frames(
            frame_out,
            frame_ref,
            tolerance=expectation.tolerance
        )

        self.process_frame_done()

    @staticmethod
    def _is_video_expectation(expectation):
        return isinstance(expectation.packet, VIPVideoPacket) or (
            expectation.packet is None and not expectation.compare
        )

    def _process_user_packet(self, packet):
        raise NotImplementedError

    async def wait_frame_checked(
        self,
        timeout=1,
        timeout_unit="ms",
        *,
        after=None,
    ):
        """Wait for one more compared or explicitly skipped output frame."""
        target = (
            self.waited_frames_cnt + 1
            if after is None
            else int(after) + 1
        )
        while self.get_frame_count() < target and self._failure is None:
            self._frame_checked.clear()
            try:
                await with_timeout(
                    self._frame_checked.wait(),
                    timeout,
                    timeout_unit,
                )
            except SimTimeoutError as exc:
                raise AssertionError(
                    f"Frame check timeout after {timeout} {timeout_unit}: "
                    f"got {self.get_frame_count()} of {target} expected frames"
                ) from exc

        if self._failure is not None:
            raise self._failure

        self.waited_frames_cnt = max(self.waited_frames_cnt, target)
