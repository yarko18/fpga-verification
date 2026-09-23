# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

from fpga_verification.protocols.avalon_st.intel_video import (
    VIPControlPacket,
    VIPUserPacket,
    VIPVideoPacket,
)
from fpga_verification.sim.scoreboards import (
    BaseVIPScoreboard,
    PacketExpectation,
    VideoPacketPolicy,
)
from fpga_verification.video import FrameSize


class StreamScoreboard(BaseVIPScoreboard):
    """Map input packets to strict ordered output expectations."""

    def __init__(self, name, parent, *, fmt, behavior_model, clock, reset):
        super().__init__(
            name,
            parent,
            source_fmt=fmt,
            sink_fmt=fmt,
            clock=clock,
            reset=reset,
            quiet_cycles=2,
        )
        self.behavior_model = behavior_model
        self.last_input_size = None

    def process_input_packet(self, packet):
        if isinstance(packet, VIPControlPacket):
            self.last_input_size = FrameSize(packet.width, packet.height)
            self.add_expectation(PacketExpectation(packet))
            return
        if isinstance(packet, VIPUserPacket):
            self.add_expectation(PacketExpectation(packet))
            return
        if not isinstance(packet, VIPVideoPacket):
            raise TypeError(f"Unsupported packet: {type(packet)!r}")
        if self.last_input_size is None:
            raise AssertionError("VIDEO packet arrived before CONTROL packet")

        frame = self.vip_input_codec.video_packet_to_frame(
            packet,
            self.last_input_size,
        )
        result = self.behavior_model.process_video_frame(frame)
        if result.policy is VideoPacketPolicy.DROP:
            return
        expected = self.vip_output_codec.frame_to_video_packet(
            result.expected,
            self.last_input_size,
        )
        self.add_expectation(
            PacketExpectation(
                expected,
                check=result.policy.value,
                tolerance=result.tolerance,
                reason=result.reason,
            )
        )

    def on_reset(self):
        self.last_input_size = None
        self.behavior_model.reset()
