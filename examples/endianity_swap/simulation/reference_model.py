# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from fpga_verification.altera.video import VIPUserPacket, VIPVideoPacket


class EndianitySwapModel:
    """Reference transformation for supported VIP packet types."""

    def __init__(self, symbols_per_beat):
        self.symbols_per_beat = int(symbols_per_beat)

    def process(self, packet):
        if isinstance(packet, VIPUserPacket):
            return VIPUserPacket(packet.user_type, list(packet.payload))
        if isinstance(packet, VIPVideoPacket):
            return VIPVideoPacket(self._swap_beats(packet.payload))
        raise TypeError(f"Unsupported packet type: {type(packet).__name__}")

    def _swap_beats(self, payload):
        converted = []
        for start in range(0, len(payload), self.symbols_per_beat):
            beat = payload[start : start + self.symbols_per_beat]
            converted.extend(reversed(beat))
        return converted
