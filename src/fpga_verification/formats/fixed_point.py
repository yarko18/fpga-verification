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

from numbers import Integral

import numpy as np

from .integer import unsigned_storage_dtype


class QFormat:
    """Fixed-point values stored as unsigned raw two's-complement words.

    ``qi`` includes the sign bit when ``signed`` is true. For example,
    ``QFormat(3, 0, signed=True)`` represents signed 3-bit integer values.
    """

    def __init__(self, qi, qf, signed=True):
        if not isinstance(qi, Integral) or not isinstance(qf, Integral):
            raise TypeError("Q-format integer and fractional widths must be integers")
        if qi < 1:
            raise ValueError("Q-format integer width must be greater than zero")
        if qf < 0:
            raise ValueError("Q-format fractional width must not be negative")

        self.qi = int(qi)
        self.qf = int(qf)
        self.signed = bool(signed)
        self.width = self.qi + self.qf
        if self.width > 63:
            raise ValueError("QFormat supports widths up to 63 bits because arithmetic uses int64")
        unsigned_storage_dtype(self.width)

        self.scale = 1 << self.qf
        self.mask = (1 << self.width) - 1

        if self.signed:
            self.min_int = -(1 << (self.width - 1))
            self.max_int = (1 << (self.width - 1)) - 1
        else:
            self.min_int = 0
            self.max_int = self.mask

        self.min_float = self.min_int / self.scale
        self.max_float = self.max_int / self.scale

    @property
    def dtype(self):
        return unsigned_storage_dtype(self.width)

    def _raw_dtype(self):
        return self.dtype

    def qraw_to_int(self, raw):
        raw = np.asarray(raw, dtype=np.int64) & self.mask

        if self.signed:
            sign = 1 << (self.width - 1)
            raw = np.where(raw & sign, raw - (1 << self.width), raw)

        return raw

    def qraw_to_float(self, raw):
        return self.qraw_to_int(raw).astype(np.float64) / self.scale

    def int_to_qraw(self, raw, saturate=True):
        raw = np.asarray(raw, dtype=np.int64)

        if saturate:
            raw = np.clip(raw, self.min_int, self.max_int)

        return raw & self.mask

    def float_to_qraw(self, x, saturate=True):
        raw = np.floor(np.asarray(x, dtype=np.float64) * self.scale).astype(np.int64)
        return self.int_to_qraw(raw, saturate=saturate)

    def multiply(self, left_raw, right_format, right_raw, out_qf=None):
        left = self.qraw_to_int(left_raw)
        right = right_format.qraw_to_int(right_raw)

        raw = left * right
        product_qf = self.qf + right_format.qf

        if out_qf is None:
            return raw

        shift = product_qf - int(out_qf)
        if shift > 0:
            return raw >> shift
        if shift < 0:
            return raw << (-shift)

        return raw

    def zeros(self, size=None, dtype=None):
        return self.full(size, 0, dtype=dtype, raw=True)

    def full(self, size, value, dtype=None, raw=False, saturate=True):
        dtype = self.dtype if dtype is None else dtype

        if raw:
            raw_value = int(value) & self.mask
        else:
            raw_value = int(self.float_to_qraw(value, saturate=saturate))

        if size is None:
            return np.asarray(raw_value, dtype=dtype)[()]

        return np.full(size, raw_value, dtype=dtype)

    def ones(self, size=None, dtype=None):
        return self.full(size, 1.0, dtype=dtype, raw=False)

    def randomize(self, size=None, raw=True, dtype=None, low=None, high=None):
        if raw:
            low = 0 if low is None else int(low)
            high = self.mask if high is None else int(high)
            dtype = self.dtype if dtype is None else dtype
            return np.random.randint(low, high + 1, size=size, dtype=dtype)

        low = self.min_float if low is None else float(low)
        high = self.max_float if high is None else float(high)
        dtype = np.float64 if dtype is None else dtype
        return np.asarray(np.random.uniform(low, high, size=size), dtype=dtype)
