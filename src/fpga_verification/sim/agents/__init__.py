# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Vendor-independent simulation agent interfaces."""

from .frame_source import FrameSource, FrameTransaction

__all__ = [
    "FrameSource",
    "FrameTransaction",
]
