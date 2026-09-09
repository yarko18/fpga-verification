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

import numpy as np
from enum import IntEnum, auto
from dataclasses import dataclass

from fpga_verification.video import FrameSize
from fpga_verification.protocols.avalon_st.intel_video import (
    IntelVIPFrameCodec,
    VIPPacket,
    VIPControlPacket,
    VIPVideoPacket,
    VIPUserPacket,
)

@dataclass
class PacketExpectation:
    packet: VIPPacket | None = None
    compare: bool = True
    reason: str = ""
    tolerance: int = 0

class BaseVIPPredictor:
    class IpMode(IntEnum):
        PASSTHROUGH = 0
        ACTIVE = auto()

    def __init__(
            self, 
            model, 
            input_codec, 
            output_codec, 
            support_passthrough=False, 
            default_ip_mode=None
        ):
        self.model = model
        self.input_codec = input_codec
        self.output_codec = output_codec
        self.last_input_size = None

        self.support_passthrough = bool(support_passthrough)
        self.ip_mode = (
            default_ip_mode
            if default_ip_mode is not None
            else self.IpMode.PASSTHROUGH if self.support_passthrough else self.IpMode.ACTIVE
        )
    
    def set_mode(self, mode):
        mode = self.IpMode(mode)

        if mode == self.IpMode.PASSTHROUGH and not self.support_passthrough:
            raise ValueError("This IP does not support passthrough mode")

        self.ip_mode = mode

    def process_packet(self, packet) -> PacketExpectation:
        if isinstance(packet, VIPControlPacket):
            return self._process_control_packet(packet)
        
        if isinstance(packet, VIPVideoPacket):
            return self._process_video_packet(packet)
        
        if isinstance(packet, VIPUserPacket):
            return self._process_user_packet(packet)

    def _process_control_packet(self, packet):
        self.last_input_size = FrameSize(packet.width, packet.height)
        
        expected_size = self.expected_output_size(self.last_input_size)
        expected_packet = self.output_codec.control_packet(expected_size, interlacing=packet.interlacing)
        
        return PacketExpectation(packet=expected_packet)

    def _process_video_packet(self, packet):
        if not self._input_video_matches_control(packet):
            return PacketExpectation(compare=False, reason="corrupted frame")
        
        frame = self.input_codec.video_packet_to_frame(packet, self.last_input_size)

        if not self.is_supported_frame_size(self.last_input_size):
            return self.unsupported_frame_expectation(frame, self.last_input_size)

        expected_frame = self.process_frame(frame, self.last_input_size)

        if expected_frame is None:
            return PacketExpectation(compare=False, reason="model output is not ready")
        
        expected_size = self.expected_output_size(self.last_input_size)

        expected_packet = self.output_codec.frame_to_video_packet(
            expected_frame,
            expected_size,
        )

        return PacketExpectation(
            packet=expected_packet,
            tolerance=self.get_tolerance()
        )

    def _process_user_packet(self, packet):
        raise NotImplementedError
    
    def _input_video_matches_control(self, packet):
        expected_symbols = self.input_codec.fmt.frame_symbol_count(
            self.last_input_size
        )
        actual_size = len(packet.payload)
        return actual_size == expected_symbols
    
    def get_tolerance(self):
        raise NotImplementedError

    def is_supported_frame_size(self, size):
        return True
    
    def expected_output_size(self, input_size):
        return input_size
    
    def unsupported_frame_expectation(self, frame, size):
        return PacketExpectation(compare=False, reason=f"unsupported frame size {size}")
    
    def process_frame(self, frame, size):
        if self.ip_mode == self.IpMode.PASSTHROUGH:
            return frame
        return self.model.process(frame)
