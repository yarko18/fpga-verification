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

        self.model = None

        self.last_input_size = None
        self.last_output_size = None
        self.input_frame_queue = deque()
        self.input_sizes_queue = deque()
        self.input_frame_valid_queue = deque()

        self.input_frames_cnt = 0
        self.output_frames_cnt = 0
        self.waited_frames_cnt = 0
        
        self._failure = None
        self._frame_checked = Event()
        self.enable_compare = True
        self.enable_passthrough = False

    def _push_input_frame(self, valid, frame, size):
        """ Store input frame and size with valid flag"""
        self.input_frame_valid_queue.append(valid)
        self.input_frame_queue.append(frame)
        self.input_sizes_queue.append(size)

    def _peek_input_frame(self):
        """ Just look at first element in queue """
        if (
            not self.input_sizes_queue
            or not self.input_frame_queue
            or not self.input_frame_valid_queue
        ):
            raise AssertionError("Unexpected output VIP video packet without input frame")

        return (
            self.input_frame_valid_queue[0],
            self.input_frame_queue[0],
            self.input_sizes_queue[0],
        )

    def _pop_input_frame(self):
        """ Get and remove first element in queue """
        if (
            not self.input_sizes_queue
            or not self.input_frame_queue
            or not self.input_frame_valid_queue
        ):
            raise AssertionError("Unexpected output VIP video packet without input frame")

        return (
            self.input_frame_valid_queue.popleft(),
            self.input_frame_queue.popleft(),
            self.input_sizes_queue.popleft(),
        )

    def process_input_packet(self, vip_packet):
        """ Each scoreboard can specify the input packet processing details for a specific IP """
        return None

    def __process_input_packet(self, vip_packet):
        """ Input VIP packets proccesing common principles """
        try:
            if isinstance(vip_packet, VIPControlPacket):
                width = vip_packet.width
                height = vip_packet.height
                
                self.last_input_size = FrameSize(width, height)

            elif isinstance(vip_packet, VIPVideoPacket):
                expected_symbols = self.vip_input_codec.fmt.frame_symbol_count(
                    self.last_input_size
                )

                actual_size = len(vip_packet.payload)

                if actual_size == expected_symbols:
                    frame = self.vip_input_codec.video_packet_to_frame(
                        vip_packet,
                        self.last_input_size
                    )
                    self._push_input_frame(True, frame, self.last_input_size)
                else:
                    self._push_input_frame(False, None, actual_size)
                    self.log.info("Input frame with size=%s missmatch"
                                  "with last input control packet size=%s",
                                  actual_size,
                                  self.last_input_size
                    )

                self.input_frames_cnt += 1

            return self.process_input_packet(vip_packet)

        except Exception as exc:
            self._failure = exc
            self._frame_checked.set()

    def process_frame_done(self):
        self.output_frames_cnt += 1
        self._frame_checked.set()

    def process_output_packet(self, vip_packet):
        """ Each scoreboard can specify the input packet processing details for a specific IP """
        return None

    def __process_output_packet(self, vip_packet):
        """ Output VIP packets proccesing common principles """
        if self._failure is not None:
            return
        try:
            if isinstance(vip_packet, VIPControlPacket):
                width = vip_packet.width
                height = vip_packet.height
                    
                self.last_output_size = FrameSize(width, height)

            elif isinstance(vip_packet, VIPVideoPacket):
                valid_in, frame_in, size_in = self._peek_input_frame()

                if not valid_in:
                    self.log.info("Output frame with size=%s will not compare due to missmatch"
                                  "with last output control packet size=%s",
                                  size_in,
                                  self.last_input_size
                    )
                    self._pop_input_frame()
                    self.process_frame_done()
                    return True

                expected_symbols = self.vip_output_codec.fmt.frame_symbol_count(
                    self.last_output_size
                )

                actual_size = len(vip_packet.payload)

                assert actual_size == expected_symbols, "Output frame size missmatch"

                frame_out = self.vip_output_codec.video_packet_to_frame(
                    vip_packet,
                    self.last_output_size
                )

                if self.enable_passthrough:
                    self.log.info("Passthrough input frame to output")
                    compare_frames(frame_in, frame_out, tolerance=0)
            
            return self.process_output_packet(vip_packet)
            
        except Exception as exc:
            self._failure = exc
            self._frame_checked.set()

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
