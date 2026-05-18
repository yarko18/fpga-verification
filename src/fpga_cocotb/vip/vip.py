# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from enum import IntEnum


class VIPPacketType(IntEnum):
    VIDEO = 0x0
    CONTROL = 0xF
    ANCILLARY = 0xD

    USER1 = 0x1
    USER2 = 0x2
    USER3 = 0x3
    USER4 = 0x4
    USER5 = 0x5
    USER6 = 0x6
    USER7 = 0x7
    USER8 = 0x8

class VIPInterlacing(IntEnum):
    PROGRESSIVE_FRAME = 0b0011
    PROGRESSIVE_FROM_F0 = 0b0000
    PROGRESSIVE_FROM_F1 = 0b0001

    INTERLACED_F0_PREV_F1 = 0b1000
    INTERLACED_F0_NEXT_F1 = 0b1001
    INTERLACED_F0_DONT_CARE = 0b1010

    INTERLACED_F1_NEXT_F0 = 0b1100
    INTERLACED_F1_PREV_F0 = 0b1101
    INTERLACED_F1_DONT_CARE = 0b1110


@dataclass
class VIPPacket:
    packet_type: VIPPacketType

    def to_symbols(self) -> list[int]:
        raise NotImplementedError

@dataclass
class VIPControlPacket(VIPPacket):
    width: int
    height: int
    interlacing: VIPInterlacing = VIPInterlacing.PROGRESSIVE_FRAME

    def __init__(
        self,
        width: int,
        height: int,
        interlacing: VIPInterlacing = VIPInterlacing.PROGRESSIVE_FRAME,
    ):
        super().__init__(VIPPacketType.CONTROL)
        self.width = width
        self.height = height
        self.interlacing = interlacing
        self.validate()

    def validate(self):
        if not 0 <= self.width <= 0xFFFF:
            raise ValueError("width must fit into 16 bits")

        if not 0 <= self.height <= 0xFFFF:
            raise ValueError("height must fit into 16 bits")

    def to_symbols(self) -> list[int]:
        return [
            int(VIPPacketType.CONTROL),
            (self.width >> 12) & 0xF,
            (self.width >> 8) & 0xF,
            (self.width >> 4) & 0xF,
            self.width & 0xF,
            (self.height >> 12) & 0xF,
            (self.height >> 8) & 0xF,
            (self.height >> 4) & 0xF,
            self.height & 0xF,
            int(self.interlacing) & 0xF,
        ]

    @classmethod
    def from_symbols(cls, symbols: list[int]):
        if len(symbols) < 10:
            raise ValueError(f"Control packet too short: {len(symbols)} symbols")

        if (symbols[0] & 0xF) != VIPPacketType.CONTROL:
            raise ValueError(f"Not a control packet: type=0x{symbols[0] & 0xF:X}")

        width = (
            ((symbols[1] & 0xF) << 12)
            | ((symbols[2] & 0xF) << 8)
            | ((symbols[3] & 0xF) << 4)
            | (symbols[4] & 0xF)
        )

        height = (
            ((symbols[5] & 0xF) << 12)
            | ((symbols[6] & 0xF) << 8)
            | ((symbols[7] & 0xF) << 4)
            | (symbols[8] & 0xF)
        )

        interlacing_raw = symbols[9] & 0xF

        return cls(
            width=width,
            height=height,
            interlacing=VIPInterlacing(interlacing_raw),
        )
    
@dataclass
class VIPVideoPacket(VIPPacket):
    payload: list[int]

    def __init__(self, payload: list[int]):
        super().__init__(VIPPacketType.VIDEO)
        self.payload = payload

    def to_symbols(self) -> list[int]:
        return [int(VIPPacketType.VIDEO)] + self.payload

    @classmethod
    def from_symbols(cls, symbols: list[int]):
        if not symbols:
            raise ValueError("Empty video packet")

        if (symbols[0] & 0xF) != VIPPacketType.VIDEO:
            raise ValueError(f"Not a VIP video packet: type=0x{symbols[0] & 0xF:X}")

        return cls(payload=list(symbols[1:]))
    
@dataclass
class VIPUserPacket(VIPPacket):
    user_type: int
    payload: list[int]

    def __init__(self, user_type: int, payload: list[int]):
        if not 1 <= user_type <= 8:
            raise ValueError("VIP user packet type must be 1..8")

        super().__init__(VIPPacketType(user_type))
        self.user_type = user_type
        self.payload = payload

    def to_symbols(self) -> list[int]:
        return [self.user_type & 0xF] + self.payload

    @classmethod
    def from_symbols(cls, symbols: list[int]):
        if not symbols:
            raise ValueError("Empty user packet")

        user_type = symbols[0] & 0xF

        if not 1 <= user_type <= 8:
            raise ValueError(f"Not a VIP user packet: type=0x{user_type:X}")

        return cls(
            user_type=user_type,
            payload=list(symbols[1:]),
        )
    
@dataclass
class VIPFrame:
    width: int
    height: int
    pixels: list[int]
    interlacing: VIPInterlacing = VIPInterlacing.PROGRESSIVE_FRAME
    user_packets: list[VIPUserPacket] = field(default_factory=list)

    def control_packet(self) -> VIPControlPacket:
        return VIPControlPacket(
            width=self.width,
            height=self.height,
            interlacing=self.interlacing,
        )

    def video_packet(self) -> VIPVideoPacket:
        return VIPVideoPacket(self.pixels)

    def packets(self) -> list[VIPPacket]:
        return [
            *self.user_packets,
            self.control_packet(),
            self.video_packet(),
        ]
    
def vip_packet_from_symbols(symbols: list[int]) -> VIPPacket:
    if not symbols:
        raise ValueError("Empty VIP packet")

    packet_type = symbols[0] & 0xF

    if packet_type == int(VIPPacketType.VIDEO):
        return VIPVideoPacket.from_symbols(symbols)

    if packet_type == int(VIPPacketType.CONTROL):
        return VIPControlPacket.from_symbols(symbols)

    if 1 <= packet_type <= 8:
        return VIPUserPacket.from_symbols(symbols)

    if packet_type == int(VIPPacketType.ANCILLARY):
        raise NotImplementedError("Ancillary VIP packet is not implemented yet")

    raise ValueError(f"Reserved/unsupported VIP packet type: 0x{packet_type:X}")