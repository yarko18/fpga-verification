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
    width: int = 0
    height: int = 0
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
        assert 0 <= self.width <= 0xFFFF
        assert 0 <= self.height <= 0xFFFF
        assert 0 <= int(self.interlacing) <= 0xF

    def to_symbols(self) -> list[int]:
        return [
            VIPPacketType.CONTROL,
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
        if (symbols[0] & 0xF) != VIPPacketType.CONTROL:
            raise ValueError("Not a VIP control packet")

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

        interlacing = VIPInterlacing(symbols[9] & 0xF)

        return cls(width, height, interlacing)
    
@dataclass
class VIPVideoPacket(VIPPacket):
    payload: list[int]

    def __init__(self, payload: list[int]):
        super().__init__(VIPPacketType.VIDEO)
        self.payload = payload

    def to_symbols(self) -> list[int]:
        return [VIPPacketType.VIDEO] + self.payload

    @classmethod
    def from_symbols(cls, symbols: list[int]):
        if (symbols[0] & 0xF) != VIPPacketType.VIDEO:
            raise ValueError("Not a VIP video packet")

        return cls(payload=symbols[1:])
    
@dataclass
class VIPUserPacket(VIPPacket):
    user_type: int
    payload: list[int]

    def __init__(self, user_type: int, payload: list[int]):
        if not 1 <= user_type <= 8:
            raise ValueError("User packet type must be 1..8")

        super().__init__(VIPPacketType(user_type))
        self.user_type = user_type
        self.payload = payload

    def to_symbols(self) -> list[int]:
        return [self.user_type & 0xF] + self.payload
    
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