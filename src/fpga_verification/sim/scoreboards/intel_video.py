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

"""Strict ordered scoreboard engine for Intel Avalon-ST Video packets."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from enum import Enum

import cocotb
from cocotb.triggers import Edge, Event, First, RisingEdge, SimTimeoutError, with_timeout
from pyuvm import uvm_scoreboard

from fpga_verification.protocols.avalon_st.intel_video import (
    IntelVIPFrameCodec,
    VIPControlPacket,
    VIPPacket,
    VIPUserPacket,
    VIPVideoPacket,
)
from fpga_verification.sim.scoreboards.analysis import AnalysisImp
from fpga_verification.video import FrameSize, compare_frames


class CheckMode(str, Enum):
    """How an expected packet is verified."""

    EXACT = "exact"
    SHAPE = "shape"


class UserPacketPolicy(str, Enum):
    """Default input-user-packet policy for custom VIP scoreboards."""

    DROP = "drop"
    PASSTHROUGH = "passthrough"


@dataclass(frozen=True)
class PacketExpectation:
    """One expected output packet and its explicit comparison contract."""

    packet: VIPPacket
    check: CheckMode = CheckMode.EXACT
    reason: str = ""
    tolerance: int = 0

    def __post_init__(self):
        if not isinstance(self.packet, VIPPacket):
            raise TypeError("PacketExpectation.packet must be a VIPPacket")
        object.__setattr__(self, "check", CheckMode(self.check))
        if int(self.tolerance) < 0:
            raise ValueError("PacketExpectation.tolerance must be >= 0")


class BaseVIPScoreboard(uvm_scoreboard):
    """Ordered protocol-level comparison engine for one VIP output stream.

    Subclasses implement IP semantics through ``process_input_packet()``,
    ``process_control_transaction()`` and ``on_reset()``.  They create all
    expectations explicitly with :meth:`add_expectation`; this base class only
    enforces packet order and the selected protocol-level comparison mode.
    """

    def __init__(
        self,
        name,
        parent,
        source_fmt=None,
        sink_fmt=None,
        *,
        clock=None,
        reset=None,
        reset_active_level=True,
        quiet_cycles=0,
    ):
        super().__init__(name, parent)
        if sink_fmt is None:
            raise ValueError("sink_fmt must be provided")
        if int(quiet_cycles) < 0:
            raise ValueError("quiet_cycles must be >= 0")

        self.data_in_export = (
            AnalysisImp("data_in_export", self, self._process_input_packet)
            if source_fmt is not None
            else None
        )
        self.data_out_export = AnalysisImp(
            "data_out_export", self, self._process_output_packet
        )
        self.control_export = AnalysisImp(
            "control_export", self, self._process_control_transaction
        )
        self.log = logging.getLogger(f"cocotb.base_vip_scoreboard.{name}")

        self.vip_input_codec = (
            IntelVIPFrameCodec(source_fmt) if source_fmt is not None else None
        )
        self.vip_output_codec = IntelVIPFrameCodec(sink_fmt)
        self.clock = clock
        self.reset_signal = reset
        self.reset_active_level = bool(reset_active_level)
        self.quiet_cycles = int(quiet_cycles)
        self._in_reset = False

        self.expected_queue = deque()
        self.last_output_size = None
        self.protocol_epoch = 0
        self.input_frames_cnt = 0
        self.output_frames_cnt = 0
        self.waited_frames_cnt = 0

        self._failure = None
        self._frame_checked = Event()
        self._queue_changed = Event()
        self._output_seen = Event()
        self._reset_task = None

    def add_expectation(self, expectation: PacketExpectation):
        """Append exactly one output packet expectation in protocol order."""
        if not isinstance(expectation, PacketExpectation):
            raise TypeError("expectation must be a PacketExpectation")
        if self._failure is not None:
            return
        self.expected_queue.append(expectation)
        self._queue_changed.set()

    def process_input_packet(self, packet: VIPPacket):
        """Map an observed input packet to zero or more output expectations."""

    def process_control_transaction(self, transaction):
        """Apply an observed Avalon-MM/control transaction to IP state."""

    def on_reset(self):
        """Reset transient custom-scoreboard/behaviour-model state."""

    def get_frame_count(self):
        return self.output_frames_cnt

    def process_frame_done(self):
        self.output_frames_cnt += 1
        self._frame_checked.set()

    def _record_failure(self, exc):
        if self._failure is None:
            self._failure = exc
        self._frame_checked.set()
        self._queue_changed.set()
        self._output_seen.set()

    def _raise_failure(self):
        if self._failure is not None:
            raise self._failure

    def _process_input_packet(self, packet):
        if self._in_reset or self._failure is not None:
            return
        try:
            self.process_input_packet(packet)
            if isinstance(packet, VIPVideoPacket):
                self.input_frames_cnt += 1
        except Exception as exc:
            self._record_failure(exc)

    def _process_control_transaction(self, transaction):
        if self._in_reset or self._failure is not None:
            return
        try:
            self.process_control_transaction(transaction)
        except Exception as exc:
            self._record_failure(exc)

    def _process_output_packet(self, packet):
        """Match one observed output packet against the next expectation."""
        self._output_seen.set()
        if self._in_reset or self._failure is not None:
            return
        try:
            if not self.expected_queue:
                raise AssertionError(f"Unexpected output {self._packet_name(packet)} packet")

            expectation = self.expected_queue[0]
            if type(packet) is not type(expectation.packet):
                raise AssertionError(
                    f"Unexpected output {self._packet_name(packet)} packet; "
                    f"expected {self._packet_name(expectation.packet)}"
                )

            self.expected_queue.popleft()
            self._queue_changed.set()
            self._compare_packet(packet, expectation)
            if isinstance(packet, VIPControlPacket):
                self.last_output_size = FrameSize(packet.width, packet.height)
            if isinstance(packet, VIPVideoPacket):
                self.process_frame_done()
        except Exception as exc:
            self._record_failure(exc)

    @staticmethod
    def _packet_name(packet):
        if isinstance(packet, VIPControlPacket):
            return "CONTROL"
        if isinstance(packet, VIPVideoPacket):
            return "VIDEO"
        if isinstance(packet, VIPUserPacket):
            return f"USER{packet.user_type}"
        return getattr(getattr(packet, "packet_type", None), "name", "UNKNOWN")

    def _compare_packet(self, packet, expectation):
        packet_ref = expectation.packet
        if expectation.check is CheckMode.SHAPE:
            self._compare_shape(packet, packet_ref)
            return

        if isinstance(packet, VIPControlPacket):
            self._compare_control_packet(packet, packet_ref)
        elif isinstance(packet, VIPUserPacket):
            self._compare_user_packet(packet, packet_ref, exact=True)
        elif isinstance(packet, VIPVideoPacket):
            self._compare_video_packet(packet, packet_ref, expectation.tolerance)
        else:
            raise AssertionError(f"Unsupported VIP packet type: {packet.packet_type}")

    def _compare_shape(self, packet, packet_ref):
        if isinstance(packet, VIPControlPacket):
            self._compare_control_packet(packet, packet_ref)
        elif isinstance(packet, VIPUserPacket):
            self._compare_user_packet(packet, packet_ref, exact=False)
        elif isinstance(packet, VIPVideoPacket):
            assert len(packet.payload) == len(packet_ref.payload), (
                f"expected VIDEO payload length {len(packet_ref.payload)}, "
                f"got {len(packet.payload)}"
            )
        else:
            raise AssertionError(f"Unsupported VIP packet type: {packet.packet_type}")

    @staticmethod
    def _compare_control_packet(packet, packet_ref):
        assert packet_ref.width == packet.width, (
            f"expected width {packet_ref.width}, got {packet.width}"
        )
        assert packet_ref.height == packet.height, (
            f"expected height {packet_ref.height}, got {packet.height}"
        )
        assert packet.interlacing.is_interlaced == packet_ref.interlacing.is_interlaced, (
            f"expected interlacing {packet_ref.interlacing}, "
            f"got {packet.interlacing}"
        )

    @staticmethod
    def _compare_user_packet(packet, packet_ref, *, exact):
        assert packet.user_type == packet_ref.user_type, (
            f"expected USER{packet_ref.user_type}, got USER{packet.user_type}"
        )
        if exact:
            assert packet.payload == packet_ref.payload, "USER payload mismatch"
        else:
            assert len(packet.payload) == len(packet_ref.payload), (
                f"expected USER payload length {len(packet_ref.payload)}, "
                f"got {len(packet.payload)}"
            )

    def _compare_video_packet(self, packet, packet_ref, tolerance):
        if self.last_output_size is None:
            raise AssertionError("VIDEO packet arrived before CONTROL packet")
        frame_ref = self.vip_output_codec.video_packet_to_frame(packet_ref, self.last_output_size)
        frame_out = self.vip_output_codec.video_packet_to_frame(packet, self.last_output_size)
        compare_frames(frame_out, frame_ref, tolerance=int(tolerance))

    def _reset_active(self):
        return bool(int(self.reset_signal.value)) == self.reset_active_level

    def reset(self):
        """Abort pending protocol work while preserving an already-found error."""
        self._in_reset = True
        self.expected_queue.clear()
        self.last_output_size = None
        self.protocol_epoch += 1
        self._queue_changed.set()
        try:
            self.on_reset()
        except Exception as exc:
            self._record_failure(exc)

    async def _watch_reset(self):
        if self._reset_active():
            self.reset()
        while True:
            trigger = getattr(self.reset_signal, "value_change", None)
            await trigger if trigger is not None else Edge(self.reset_signal)
            if self._reset_active():
                self.reset()
            else:
                self._in_reset = False

    async def run_phase(self):
        if self.reset_signal is not None:
            self._reset_task = cocotb.start_soon(self._watch_reset())

    def check_phase(self):
        self._raise_failure()
        if self.expected_queue:
            raise AssertionError(
                f"Missing output packets: {len(self.expected_queue)} expectation(s) remain"
            )

    async def wait_frame_checked(self, timeout=1, timeout_unit="ms", *, after=None):
        """Wait until one more expected VIDEO packet has been checked."""
        target = self.waited_frames_cnt + 1 if after is None else int(after) + 1
        while self.get_frame_count() < target and self._failure is None:
            self._frame_checked.clear()
            try:
                await with_timeout(self._frame_checked.wait(), timeout, timeout_unit)
            except SimTimeoutError as exc:
                raise AssertionError(
                    f"Frame check timeout after {timeout} {timeout_unit}: "
                    f"got {self.get_frame_count()} of {target} expected frames"
                ) from exc
        self._raise_failure()
        self.waited_frames_cnt = max(self.waited_frames_cnt, target)

    async def drain(self, timeout, timeout_unit="ms", *, quiet_cycles=None):
        """Wait for all expectations, then require a quiet output window.

        An output packet during the quiet window is always a failure: by then
        there is no matching expectation left.  ``quiet_cycles=0`` disables the
        additional observation window.
        """
        while self.expected_queue and self._failure is None:
            self._queue_changed.clear()
            try:
                await with_timeout(self._queue_changed.wait(), timeout, timeout_unit)
            except SimTimeoutError as exc:
                raise AssertionError(
                    f"Drain timeout after {timeout} {timeout_unit}: "
                    f"{len(self.expected_queue)} expectation(s) remain"
                ) from exc

        self._raise_failure()
        cycles = self.quiet_cycles if quiet_cycles is None else int(quiet_cycles)
        if cycles < 0:
            raise ValueError("quiet_cycles must be >= 0")
        if cycles == 0:
            return
        if self.clock is None:
            raise RuntimeError("drain quiet window requires scoreboard clock")

        for _ in range(cycles):
            self._output_seen.clear()
            await First(RisingEdge(self.clock), self._output_seen.wait())
            self._raise_failure()
            if self._output_seen.is_set():
                raise AssertionError("Unexpected output packet during drain quiet window")
