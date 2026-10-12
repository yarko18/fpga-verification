# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Vendor-independent video frame primitives."""

from .core import (
    FrameSize,
    compare_frames,
)

__all__ = [
    "FrameSize",
    "compare_frames",
]
