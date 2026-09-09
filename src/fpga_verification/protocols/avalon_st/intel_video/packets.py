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

"""Packet codecs for the Intel Avalon-ST Video protocol."""

from dataclasses import dataclass, field
from enum import IntEnum


def _validate_symbols_per_beat(symbols_per_beat):
    symbols_per_beat = int(symbols_per_beat)
    if symbols_per_beat <= 0:
        raise ValueError("symbols_per_beat must be > 0")
    return symbols_per_beat


def _encode_packet(packet_type, payload, symbols_per_beat, *, pad_payload):
    symbols_per_beat = _validate_symbols_per_beat(symbols_per_beat)
    payload = [int(symbol) for symbol in payload]
    padding = (-len(payload)) % symbols_per_beat if pad_payload else 0
    return [
        int(packet_type),
        *([0] * (symbols_per_beat - 1)),
        *payload,
        *([0] * padding),
    ]


def _decode_payload(
    symbols,
    packet_type,
    symbols_per_beat,
    *,
    require_complete_beats,
):
    symbols_per_beat = _validate_symbols_per_beat(symbols_per_beat)
    symbols = [int(symbol) for symbol in symbols]
    if not symbols:
        raise ValueError("Empty VIP packet")
    if len(symbols) < symbols_per_beat:
        raise ValueError("VIP packet must contain a complete identifier beat")
    if require_complete_beats and len(symbols) % symbols_per_beat:
        raise ValueError("VIP packet symbol count must contain complete beats")
    if (symbols[0] & 0xF) != int(packet_type):
        raise ValueError(
            f"Unexpected VIP packet type: 0x{symbols[0] & 0xF:X}"
        )
    if any(symbol != 0 for symbol in symbols[1:symbols_per_beat]):
        raise ValueError("VIP identifier beat padding must be zero")
    return symbols[symbols_per_beat:]


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

class VIPInterlacing:
    PROGRESSIVE_FROM_F0     = 0b0000
    PROGRESSIVE_FROM_F1     = 0b0001
    PROGRESSIVE_FRAME       = 0b0010

    INTERLACED_F0_PREV_F1   = 0b1000
    INTERLACED_F0_NEXT_F1   = 0b1001
    INTERLACED_F0_DONT_CARE = 0b1010

    INTERLACED_F1_NEXT_F0   = 0b1100
    INTERLACED_F1_PREV_F0   = 0b1101
    INTERLACED_F1_DONT_CARE = 0b1110

    def __init__(self, value: int = PROGRESSIVE_FRAME):
        self.value = int(value) & 0xF

    def __int__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, VIPInterlacing):
            return self.value == other.value
        return self.value == int(other)

    def __repr__(self):
        return f"VIPInterlacing(0x{self.value:X}, {self.description})"

    @property
    def is_interlaced(self) -> bool:
        return bool(self.value & 0b1000)

    @property
    def is_progressive(self) -> bool:
        return not self.is_interlaced

    @property
    def is_progressive_from_f0(self) -> bool:
        return (self.value & 0b1011) == 0b0000

    @property
    def is_progressive_from_f1(self) -> bool:
        return (self.value & 0b1011) == 0b0001

    @property
    def is_progressive_frame(self) -> bool:
        # 0 x 1 x
        return (self.value & 0b1010) == 0b0010

    @property
    def is_f0(self) -> bool:
        # 1 0 x x
        return (self.value & 0b1100) == 0b1000

    @property
    def is_f1(self) -> bool:
        # 1 1 x x
        return (self.value & 0b1100) == 0b1100

    @property
    def description(self) -> str:
        if self.is_progressive_frame:
            return "progressive frame"

        if self.is_progressive_from_f0:
            return "progressive frame deinterlaced from F0"

        if self.is_progressive_from_f1:
            return "progressive frame deinterlaced from F1"

        if self.value == 0b1000:
            return "interlaced F0, paired with preceding F1"

        if self.value == 0b1001:
            return "interlaced F0, paired with following F1"

        if (self.value & 0b1110) == 0b1010:
            return "interlaced F0, pairing don't care"

        if self.value == 0b1100:
            return "interlaced F1, paired with following F0"

        if self.value == 0b1101:
            return "interlaced F1, paired with preceding F0"

        if (self.value & 0b1110) == 0b1110:
            return "interlaced F1, pairing don't care"

        return "unknown"


@dataclass
class VIPPacket:
    packet_type: VIPPacketType

    def to_symbols(self, symbols_per_beat: int = 1) -> list[int]:
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
        interlacing: VIPInterlacing | int = VIPInterlacing.PROGRESSIVE_FRAME,
    ):
        super().__init__(VIPPacketType.CONTROL)
        self.width = width
        self.height = height
        self.interlacing = (
            interlacing
            if isinstance(interlacing, VIPInterlacing)
            else VIPInterlacing(interlacing)
        )
        self.validate()

    def validate(self):
        if not 0 <= self.width <= 0xFFFF:
            raise ValueError("width must fit into 16 bits")

        if not 0 <= self.height <= 0xFFFF:
            raise ValueError("height must fit into 16 bits")

    def to_symbols(self, symbols_per_beat: int = 1) -> list[int]:
        payload = [
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
        return _encode_packet(
            VIPPacketType.CONTROL,
            payload,
            symbols_per_beat,
            pad_payload=True,
        )

    @classmethod
    def from_symbols(cls, symbols: list[int], symbols_per_beat: int = 1):
        payload = _decode_payload(
            symbols,
            VIPPacketType.CONTROL,
            symbols_per_beat,
            require_complete_beats=True,
        )

        if len(payload) < 9:
            raise ValueError(f"Control packet too short: {len(payload)} payload symbols")
        if any(symbol != 0 for symbol in payload[9:]):
            raise ValueError("Control packet padding must be zero")

        width = (
            ((payload[0] & 0xF) << 12)
            | ((payload[1] & 0xF) << 8)
            | ((payload[2] & 0xF) << 4)
            | (payload[3] & 0xF)
        )

        height = (
            ((payload[4] & 0xF) << 12)
            | ((payload[5] & 0xF) << 8)
            | ((payload[6] & 0xF) << 4)
            | (payload[7] & 0xF)
        )

        interlacing_raw = payload[8] & 0xF

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

    def to_symbols(self, symbols_per_beat: int = 1) -> list[int]:
        return _encode_packet(
            VIPPacketType.VIDEO,
            self.payload,
            symbols_per_beat,
            pad_payload=False,
        )

    @classmethod
    def from_symbols(cls, symbols: list[int], symbols_per_beat: int = 1):
        return cls(
            payload=_decode_payload(
                symbols,
                VIPPacketType.VIDEO,
                symbols_per_beat,
                require_complete_beats=False,
            )
        )
    
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

    def to_symbols(self, symbols_per_beat: int = 1) -> list[int]:
        return _encode_packet(
            self.packet_type,
            self.payload,
            symbols_per_beat,
            pad_payload=False,
        )

    @classmethod
    def from_symbols(cls, symbols: list[int], symbols_per_beat: int = 1):
        if not symbols:
            raise ValueError("Empty user packet")

        user_type = int(symbols[0]) & 0xF

        if not 1 <= user_type <= 8:
            raise ValueError(f"Not a VIP user packet: type=0x{user_type:X}")

        return cls(
            user_type=user_type,
            payload=_decode_payload(
                symbols,
                VIPPacketType(user_type),
                symbols_per_beat,
                require_complete_beats=False,
            ),
        )
    
@dataclass
class VIPFrame:
    width: int
    height: int
    pixels: list[int]
    interlacing: VIPInterlacing | int = VIPInterlacing.PROGRESSIVE_FRAME
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
    
def vip_packet_from_symbols(
    symbols: list[int],
    symbols_per_beat: int = 1,
) -> VIPPacket:
    if not symbols:
        raise ValueError("Empty VIP packet")

    packet_type = symbols[0] & 0xF

    if packet_type == int(VIPPacketType.VIDEO):
        return VIPVideoPacket.from_symbols(
            symbols,
            symbols_per_beat=symbols_per_beat,
        )

    if packet_type == int(VIPPacketType.CONTROL):
        return VIPControlPacket.from_symbols(
            symbols,
            symbols_per_beat=symbols_per_beat,
        )

    if 1 <= packet_type <= 8:
        return VIPUserPacket.from_symbols(
            symbols,
            symbols_per_beat=symbols_per_beat,
        )

    if packet_type == int(VIPPacketType.ANCILLARY):
        raise NotImplementedError("Ancillary VIP packet is not implemented yet")

    raise ValueError(f"Reserved/unsupported VIP packet type: 0x{packet_type:X}")
