# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from ._version import __version__
from .video import FrameSize, compare_frames

__all__ = [
    "FrameSize",
    "__version__",
    "compare_frames",
]
