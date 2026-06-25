# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""Simulator-independent image generation and video payload codecs."""

from .core import (
    FrameSize,
    ImageGenerator,
    VideoFormat,
    VideoPayloadCodec,
    compare_frames,
)

__all__ = [
    "FrameSize",
    "ImageGenerator",
    "VideoFormat",
    "VideoPayloadCodec",
    "compare_frames",
]
