# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Small analysis-port primitives independent of pyuvm.

Protocol monitors, coverage collectors, scoreboards and reference models only
need a one-way ``write(transaction)`` contract. Keeping that contract in plain
Python lets the same subscribers be connected directly or adapted to a pyuvm
analysis export at an environment boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, Protocol, TypeVar, runtime_checkable


TransactionT = TypeVar("TransactionT")


@runtime_checkable
class Subscriber(Protocol[TransactionT]):
    """Consumer of analysis transactions."""

    def write(self, item: TransactionT) -> None:
        """Consume one transaction without taking ownership of it."""


class CallbackSubscriber(Generic[TransactionT]):
    """Adapt a callable to the :class:`Subscriber` contract."""

    def __init__(self, callback: Callable[[TransactionT], object]):
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._callback = callback

    def write(self, item: TransactionT) -> None:
        self._callback(item)


class AnalysisPort(Generic[TransactionT]):
    """Synchronous one-to-many transaction broadcaster.

    This mirrors the useful part of a UVM analysis port without requiring a
    component hierarchy. A pyuvm monitor can use its native analysis port and
    connect a subscriber through ``AnalysisImp`` instead.
    """

    def __init__(self, name: str):
        if not name:
            raise ValueError("analysis port name must not be empty")
        self.name = name
        self._subscribers: list[Subscriber[TransactionT]] = []

    def connect(self, subscriber: Subscriber[TransactionT]) -> None:
        if not isinstance(subscriber, Subscriber):
            raise TypeError("analysis subscriber must provide write(item)")
        if subscriber not in self._subscribers:
            self._subscribers.append(subscriber)

    def disconnect(self, subscriber: Subscriber[TransactionT]) -> None:
        self._subscribers.remove(subscriber)

    def write(self, item: TransactionT) -> None:
        for subscriber in tuple(self._subscribers):
            subscriber.write(item)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
