# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Contract for non-VIP frame conduits used as verification sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fpga_verification.video import FrameSize


@dataclass(frozen=True)
class FrameTransaction:
    """A frame published before its source drives physical conduit signals."""

    frame: object
    size: FrameSize


class FrameSource(Protocol):
    """A source with lifecycle and analysis publication compatible with VIP tests."""

    analysis_port: object

    async def send_frame(self, frame) -> None:
        """Publish ``FrameTransaction`` then physically drive ``frame``."""

    def stop_tasks(self) -> None:
        """Stop source-owned clocks and background drive tasks."""
