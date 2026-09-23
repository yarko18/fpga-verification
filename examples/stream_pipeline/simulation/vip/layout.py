# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

from dataclasses import dataclass

from fpga_verification.video import FrameSize, VideoFormat

from .config import TestConfig


@dataclass(frozen=True)
class StreamLayout:
    """Derived stream format and active frame geometry."""

    stream_format: VideoFormat
    frame_size: FrameSize

    @classmethod
    def from_config(cls, cfg: TestConfig):
        return cls(
            stream_format=VideoFormat(
                bits_per_color=cfg.bits_per_symbol,
                number_of_color_planes=1,
                pixels_in_parallel=cfg.symbols_per_beat,
            ),
            frame_size=FrameSize(cfg.frame_width, cfg.frame_height),
        )
