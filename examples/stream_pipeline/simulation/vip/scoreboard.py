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

    def process_input_packet(self, packet):
        if isinstance(packet, (VIPControlPacket, VIPUserPacket)):
            self.add_expectation(PacketExpectation(packet))
            return
        if not isinstance(packet, VIPVideoPacket):
            raise TypeError(f"Unsupported packet: {type(packet)!r}")

        result = self.behavior_model.process_video_payload(packet.payload)
        if result.policy is VideoPacketPolicy.DROP:
            return
        expected = VIPVideoPacket(result.expected)
        self.add_expectation(
            PacketExpectation(
                expected,
                check=result.policy.value,
                tolerance=result.tolerance,
                reason=result.reason,
            )
        )

    def on_reset(self):
        self.behavior_model.reset()
