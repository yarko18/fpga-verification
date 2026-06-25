# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""Stateless numpy frame adapters for Intel Avalon-ST Video packets."""

from fpga_verification.video import FrameSize, VideoFormat, VideoPayloadCodec

from .packets import (
    VIPControlPacket,
    VIPFrame,
    VIPInterlacing,
    VIPPacket,
    VIPUserPacket,
    VIPVideoPacket,
    vip_packet_from_symbols,
)


class IntelVIPFrameCodec:
    """Pure adapters between explicit frame data and Intel VIP packets."""

    def __init__(self, fmt):
        if not isinstance(fmt, VideoFormat):
            raise TypeError("fmt must be a VideoFormat")
        self.fmt = fmt
        self.payload_codec = VideoPayloadCodec(fmt)

    @property
    def symbols_per_beat(self):
        return self.fmt.samples_per_beat

    def control_packet(
        self,
        size,
        interlacing=VIPInterlacing.PROGRESSIVE_FRAME,
    ):
        size = _require_frame_size(size)
        return VIPControlPacket(
            width=size.width,
            height=size.height,
            interlacing=interlacing,
        )

    def frame_to_video_packet(self, frame, size):
        size = _require_frame_size(size)
        return VIPVideoPacket(
            self.payload_codec.frame_to_symbols(frame, size)
        )

    def video_packet_to_frame(self, packet, size):
        size = _require_frame_size(size)
        if not isinstance(packet, VIPVideoPacket):
            raise TypeError("packet must be a VIPVideoPacket")
        return self.payload_codec.symbols_to_frame(packet.payload, size)

    def validate_control_packet(self, packet, size):
        size = _require_frame_size(size)
        if not isinstance(packet, VIPControlPacket):
            raise TypeError("packet must be a VIPControlPacket")
        if packet.width != size.width or packet.height != size.height:
            raise ValueError(
                "VIP control resolution mismatch: "
                f"got {packet.width}x{packet.height}, "
                f"expected {size.width}x{size.height}"
            )
        return True

    def frame_to_vip(
        self,
        frame,
        size,
        interlacing=VIPInterlacing.PROGRESSIVE_FRAME,
        user_packets=None,
    ):
        size = _require_frame_size(size)
        video_packet = self.frame_to_video_packet(frame, size)
        return VIPFrame(
            width=size.width,
            height=size.height,
            pixels=list(video_packet.payload),
            interlacing=interlacing,
            user_packets=list(user_packets or []),
        )

    encode_frame = frame_to_vip

    def vip_to_frame(self, vip_frame, size):
        _require_frame_size(size)
        if not isinstance(vip_frame, VIPFrame):
            raise TypeError("vip_frame must be a VIPFrame")
        return self.video_packet_to_frame(vip_frame.video_packet(), size)

    decode_frame = vip_to_frame

    def frame_to_packets(
        self,
        frame,
        size,
        interlacing=VIPInterlacing.PROGRESSIVE_FRAME,
        user_packets=None,
    ):
        size = _require_frame_size(size)
        return [
            *list(user_packets or []),
            self.control_packet(size, interlacing),
            self.frame_to_video_packet(frame, size),
        ]

    def packets_to_frame(self, packets, size):
        size = _require_frame_size(size)
        packets = list(packets)
        for packet in packets:
            if not isinstance(packet, VIPPacket):
                raise TypeError("packets must contain VIPPacket instances")

        video_packets = [
            packet for packet in packets if isinstance(packet, VIPVideoPacket)
        ]
        if len(video_packets) != 1:
            raise ValueError(
                f"expected exactly one VIP video packet, got {len(video_packets)}"
            )
        return self.video_packet_to_frame(video_packets[0], size)

    def frame_to_packet_symbols(self, frame, size, **kwargs):
        return [
            packet.to_symbols(self.symbols_per_beat)
            for packet in self.frame_to_packets(frame, size, **kwargs)
        ]

    def packet_symbols_to_frame(self, packet_symbols, size):
        packets = [
            vip_packet_from_symbols(symbols, self.symbols_per_beat)
            for symbols in packet_symbols
        ]
        return self.packets_to_frame(packets, size)


def _require_frame_size(size):
    if not isinstance(size, FrameSize):
        raise TypeError("size must be a FrameSize")
    return size
