# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5


class StreamFunctionalModel:
    """Reverse byte order independently in each video payload beat."""

    def __init__(self, bytes_per_beat):
        self.bytes_per_beat = int(bytes_per_beat)
        if self.bytes_per_beat < 2:
            raise ValueError("bytes_per_beat must be at least 2")

    def process_payload(self, payload):
        result = list(payload)
        for start in range(0, len(result), self.bytes_per_beat):
            stop = min(start + self.bytes_per_beat, len(result))
            result[start:stop] = reversed(result[start:stop])
        return result
