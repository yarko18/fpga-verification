# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

from fpga_verification.sim.scoreboards import VideoPacketResult

from .functional_model import StreamFunctionalModel


class StreamBehaviorModel:
    """Visible component behavior, kept explicit for lifecycle consistency."""

    def __init__(self, bytes_per_beat):
        self.functional_model = StreamFunctionalModel(bytes_per_beat)

    def process_video_payload(self, payload):
        return VideoPacketResult.exact(
            self.functional_model.process_payload(payload)
        )

    def reset(self):
        """The example has no retained state."""
