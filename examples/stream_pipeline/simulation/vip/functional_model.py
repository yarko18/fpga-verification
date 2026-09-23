# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

import numpy as np


class StreamFunctionalModel:
    """Pure value transformation used by the example pipeline."""

    def process_frame(self, frame):
        return np.asarray(frame).copy()
