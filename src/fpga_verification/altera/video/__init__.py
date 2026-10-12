# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Altera Avalon-ST Video formats, packets, and codecs."""

from fpga_verification.video import FrameSize, compare_frames

from .checker import VIPProtocolChecker, VIPProtocolError
from .codec import VIPFrameCodec
from .format import ImageGenerator, VideoFormat, VideoPayloadCodec
from .packets import (
    VIPControlPacket,
    VIPFrame,
    VIPInterlacing,
    VIPPacket,
    VIPPacketType,
    VIPUserPacket,
    VIPVideoPacket,
    vip_packet_from_symbols,
)

__all__ = [
    "FrameSize",
    "ImageGenerator",
    "VIPControlPacket",
    "VIPFrame",
    "VIPFrameCodec",
    "VIPInterlacing",
    "VIPPacket",
    "VIPPacketType",
    "VIPProtocolChecker",
    "VIPProtocolError",
    "VIPUserPacket",
    "VIPVideoPacket",
    "VideoFormat",
    "VideoPayloadCodec",
    "compare_frames",
    "vip_packet_from_symbols",
]
