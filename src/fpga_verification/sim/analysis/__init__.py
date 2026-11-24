# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Plain-Python transaction consumer protocol used by coverage collectors."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable


TransactionT = TypeVar("TransactionT")


@runtime_checkable
class Subscriber(Protocol[TransactionT]):
    """Consumer of transactions through a ``write(item)`` method."""

    def write(self, item: TransactionT) -> None:
        """Consume one transaction without taking ownership of it."""
