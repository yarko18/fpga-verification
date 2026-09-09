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

from dataclasses import dataclass
from numbers import Integral

import numpy as np


def unsigned_storage_dtype(width):
    if width <= 8:
        return np.uint8
    if width <= 16:
        return np.uint16
    if width <= 32:
        return np.uint32
    if width <= 64:
        return np.uint64

    raise ValueError("Only unsigned widths up to 64 bits are supported")


@dataclass(frozen=True)
class UIntFormat:
    width: int

    def __post_init__(self):
        if not isinstance(self.width, Integral):
            raise TypeError("Unsigned width must be an integer")
        if self.width < 1:
            raise ValueError("Unsigned width must be greater than zero")
        unsigned_storage_dtype(self.width)

    @property
    def dtype(self):
        return unsigned_storage_dtype(self.width)

    @property
    def mask(self):
        return (1 << self.width) - 1

    def zeros(self, shape):
        return np.zeros(shape, dtype=self.dtype)

    def wrap(self, values):
        arr = np.asarray(values)
        if arr.dtype == object:
            wrap_scalar = np.frompyfunc(lambda value: int(value) & self.mask, 1, 1)
            return wrap_scalar(arr)
        if self.width == 64:
            return arr.astype(np.uint64, copy=False)
        return arr & self.mask

    def array(self, values, shape=None):
        arr = self.wrap(values).astype(self.dtype, copy=False)
        if shape is not None:
            arr = arr.reshape(shape)
        return arr
