# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""Reusable pyuvm scoreboards."""

from .analysis import AnalysisImp

from .intel_video import (
    BaseVIPScoreboard,
)

__all__ = [
    "AnalysisImp",
    "BaseVIPScoreboard",
]
