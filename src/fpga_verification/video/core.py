# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5
#
# Unless explicitly acquired and licensed from Licensor under another license,
# the contents of this file are subject to the Reciprocal Public License ("RPL")
# Version 1.5, or subsequent versions as allowed by the RPL, and You may not copy
# or use this file in either source code or executable form, except in compliance
# with the terms and conditions of the RPL.
#
# All software distributed under the RPL is provided strictly on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, AND LICENSOR
# HEREBY DISCLAIMS ALL SUCH WARRANTIES, INCLUDING WITHOUT LIMITATION, ANY
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, QUIET
# ENJOYMENT, OR NON-INFRINGEMENT. See the RPL for specific language governing
# rights and limitations under the RPL.

"""Vendor-independent video frame primitives."""

from dataclasses import dataclass
from numbers import Integral

import numpy as np


@dataclass(frozen=True)
class FrameSize:
    """Geometry of one video frame."""

    width: int
    height: int

    def __post_init__(self):
        for name in ("width", "height"):
            value = getattr(self, name)
            if not isinstance(value, Integral):
                raise TypeError(f"{name} must be an integer")
            if int(value) <= 0:
                raise ValueError(f"{name} must be > 0, got {value}")


def compare_frames(actual, expected, tolerance=0):
    """Assert that two frames have equal shape and values within tolerance."""

    actual = np.asarray(actual)
    expected = np.asarray(expected)
    if actual.shape != expected.shape:
        raise AssertionError(
            f"frame shape mismatch: got {actual.shape}, "
            f"expected {expected.shape}"
        )
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")

    actual_obj = actual.astype(object)
    expected_obj = expected.astype(object)
    diff = np.vectorize(
        lambda left, right: abs(int(left) - int(right)),
        otypes=[object],
    )(actual_obj, expected_obj)
    mismatch = np.asarray(diff > tolerance, dtype=bool)
    if not np.any(mismatch):
        return True

    mismatch_count = int(np.count_nonzero(mismatch))
    index = tuple(np.argwhere(mismatch)[0])
    coordinate = ", ".join(
        f"{axis}={value}"
        for axis, value in zip(("y", "x", "plane"), index)
    )
    raise AssertionError(
        f"frame mismatch: {mismatch_count} mismatches, "
        f"first at {coordinate}: got {actual[index]}, "
        f"expected {expected[index]}, diff={diff[index]}, "
        f"tolerance={tolerance}"
    )
