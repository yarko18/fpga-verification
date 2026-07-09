# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

from collections import deque

import logging
from cocotb.triggers import Event, SimTimeoutError, with_timeout
from pyuvm import uvm_analysis_export, uvm_scoreboard

from fpga_verification.video import compare_frames

from fpga_verification.protocols.avalon_st.intel_video import (
    IntelVIPFrameCodec,
    VIPControlPacket,
    VIPVideoPacket,
    VIPUserPacket,
)

from fpga_verification.sim.models.intel_video import PacketExpectation
from fpga_verification.video import FrameSize

class _AnalysisImp(uvm_analysis_export):
    def __init__(self, name, parent, write_fn):
        super().__init__(name, parent)
        self.write_fn = write_fn

    def write(self, item):
        self.write_fn(item)

class BaseVIPScoreboard(uvm_scoreboard):
    def __init__(self, name, parent, source_fmt, sink_fmt):
        super().__init__(name, parent)

        self.data_in_export = _AnalysisImp("data_in_export", self, self.__process_input_packet)
        self.data_out_export = _AnalysisImp("data_out_export", self, self.__process_output_packet)
        self.log = logging.getLogger(f"cocotb.base_vip_scoreboard.{name}")

        self.vip_input_codec = IntelVIPFrameCodec(source_fmt)
        self.vip_output_codec = IntelVIPFrameCodec(sink_fmt)

        self.predictor = None

        self.expected_queue = deque()
        self.last_output_size = None

        self.input_frames_cnt = 0
        self.output_frames_cnt = 0
        self.waited_frames_cnt = 0
        
        self._failure = None
        self._frame_checked = Event()
        self.enable_compare = True

    def process_frame_done(self):
        self.output_frames_cnt += 1
        self._frame_checked.set()

    def __process_input_packet(self, packet):
        try:
            expectation = self.predictor.process_packet(packet)

            if expectation is not None:
                self.expected_queue.append(expectation)

            if isinstance(packet, VIPVideoPacket):
                self.input_frames_cnt += 1

        except Exception as exc:
            self._failure = exc
            self._frame_checked.set()

    def __process_output_packet(self, packet):
        """ Output VIP packets proccesing common principles """
        if self._failure is not None:
            return
        try:
            if not self.expected_queue:
                raise AssertionError(f"Unexpected output {packet.packet_type} packet")
            
            if isinstance(packet, VIPControlPacket):
                self._process_control_packet(packet)

            elif isinstance(packet, VIPVideoPacket):
                self._process_video_packet(packet)

            elif isinstance(packet, VIPUserPacket):
                self._process_user_packet(packet)
            
            else:
                raise AssertionError(f"Unknown packet type: {packet.packet_type}")
            
        except Exception as exc:
            self._failure = exc
            self._frame_checked.set()

    def _process_control_packet(self, packet):
        expectation = self.expected_queue.popleft()
        packet_ref = expectation.packet
        assert isinstance(packet_ref, VIPControlPacket)

        self.last_output_size = FrameSize(packet.width, packet.height)

        if expectation.compare:
            assert packet_ref.width == packet.width
            assert packet_ref.height == packet.height
            assert packet_ref.interlacing == packet.interlacing
    
    def _process_video_packet(self, packet):
        expectation = self.expected_queue.popleft()

        if not expectation.compare:
            self.log.info("Skip frame compare: %s", expectation.reason)
            self.process_frame_done()
            return

        packet_ref = expectation.packet
        assert isinstance(packet_ref, VIPVideoPacket)
                
        frame_ref = self.vip_output_codec.video_packet_to_frame(
            packet_ref,
            self.last_output_size
        )

        frame_out = self.vip_output_codec.video_packet_to_frame(
            packet,
            self.last_output_size
        )

        if self.enable_compare:
            compare_frames(
                frame_out,
                frame_ref,
                tolerance=expectation.tolerance
            )

        self.process_frame_done()
    
    def _process_user_packet(self, packet):
        raise NotImplementedError
    

    async def wait_frame_checked(self, timeout=1, timeout_unit="ms"):
        """ Wait until dut process the input frame and generate the output frame """
        target_frames_cnt = self.waited_frames_cnt + 1

        while self.output_frames_cnt < target_frames_cnt and self._failure is None:
            self._frame_checked.clear()
            try:
                await with_timeout(self._frame_checked.wait(), timeout, timeout_unit)
            except SimTimeoutError as exc:
                raise AssertionError(
                    f"Output frame check timeout after {timeout} {timeout_unit}: "
                    f"checked {self.output_frames_cnt} of {target_frames_cnt} expected frames"
                ) from exc

        if self._failure is not None:
            raise self._failure

        self.waited_frames_cnt = target_frames_cnt
