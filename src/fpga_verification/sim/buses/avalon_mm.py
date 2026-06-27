# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""Reusable Avalon-MM master BFM for cocotb tests."""

from dataclasses import dataclass
from typing import Callable

from cocotb.triggers import RisingEdge


def _signal_width(signal):
    try:
        return len(signal)
    except TypeError:
        return 1


def _mask(width):
    return (1 << width) - 1


def _check_width(name, value, width):
    value = int(value)
    if value < 0 or value > _mask(width):
        raise ValueError(f"{name}={value} does not fit in {width} bits")
    return value


def _drive(signal, value):
    signal.value = int(value)


def _read_bool(signal):
    return bool(int(signal.value))


@dataclass
class AvalonMMBus:
    """Signal bundle for an Avalon-MM master-side BFM.

    Required signals: address, writedata, write, read, readdata.
    Optional signals: waitrequest, readdatavalid, byteenable.
    """

    address: object
    writedata: object
    write: object
    read: object
    readdata: object
    waitrequest: object = None
    readdatavalid: object = None
    byteenable: object = None

    @classmethod
    def from_prefix(cls, entity, prefix):
        """Build a bus from signals named '<prefix>_<signal>' on entity."""

        def required(name):
            return getattr(entity, f"{prefix}_{name}")

        def optional(name):
            return getattr(entity, f"{prefix}_{name}", None)

        return cls(
            address=required("address"),
            writedata=required("writedata"),
            write=required("write"),
            read=required("read"),
            readdata=required("readdata"),
            waitrequest=optional("waitrequest"),
            readdatavalid=optional("readdatavalid"),
            byteenable=optional("byteenable"),
        )

    @property
    def address_width(self):
        return _signal_width(self.address)

    @property
    def data_width(self):
        return _signal_width(self.writedata)

    @property
    def byteenable_width(self):
        if self.byteenable is None:
            return 0
        return _signal_width(self.byteenable)


class AvalonMMMasterBFM:
    """Simple Avalon-MM master BFM.

    The BFM supports single-beat read/write transactions with optional
    waitrequest, readdatavalid, and byteenable. It intentionally stays below
    UVM level so tests can use it directly or wrap it in a pyuvm driver later.
    """

    def __init__(
        self,
        bus,
        clock,
        reset=None,
        *,
        read_response_latency=0,
        default_byteenable=None,
    ):
        self.bus = bus
        self.clock = clock
        self.reset = reset
        self.read_response_latency = int(read_response_latency)
        self.default_byteenable = default_byteenable

        if self.read_response_latency < 0:
            raise ValueError("read_response_latency must be non-negative")

    @classmethod
    def from_prefix(cls, entity, prefix, clock, reset=None, **kwargs):
        return cls(AvalonMMBus.from_prefix(entity, prefix), clock, reset, **kwargs)

    def init_idle(self):
        """Drive the master outputs to an idle state."""

        _drive(self.bus.address, 0)
        _drive(self.bus.writedata, 0)
        _drive(self.bus.write, 0)
        _drive(self.bus.read, 0)

        if self.bus.byteenable is not None:
            _drive(self.bus.byteenable, self._resolve_byteenable(None))

    async def wait_reset_release(self, active_value=1):
        """Wait until reset is not asserted, if a reset signal was provided."""

        if self.reset is None:
            return

        while int(self.reset.value) == int(active_value):
            await RisingEdge(self.clock)

    async def write(self, address, data, byteenable=None, timeout_cycles=None):
        """Issue one Avalon-MM write and return after it is accepted."""

        self._validate_address(address)
        self._validate_data(data)

        await RisingEdge(self.clock)
        await self._start_access(address, data, byteenable, write=1, read=0)
        await self._wait_accepted(timeout_cycles)
        self._end_access()

    async def read(self, address, byteenable=None, timeout_cycles=None):
        """Issue one Avalon-MM read and return the sampled readdata value."""

        self._validate_address(address)

        await RisingEdge(self.clock)
        await self._start_access(address, 0, byteenable, write=0, read=1)
        await self._wait_accepted(timeout_cycles)
        self._end_access()

        if self.bus.readdatavalid is not None:
            await self._wait_readdatavalid(timeout_cycles)
        else:
            for _ in range(self.read_response_latency):
                await RisingEdge(self.clock)

        return int(self.bus.readdata.value)

    async def read_modify_write(
        self,
        address,
        update: Callable[[int], int],
        byteenable=None,
        timeout_cycles=None,
    ):
        """Read a register, write back update(old), and return (old, new)."""

        old_value = await self.read(address, byteenable, timeout_cycles)
        new_value = int(update(old_value))
        await self.write(address, new_value, byteenable, timeout_cycles)
        return old_value, new_value

    async def poll(
        self,
        address,
        predicate: Callable[[int], bool],
        *,
        interval_cycles=1,
        timeout_cycles=None,
    ):
        """Read address until predicate(value) is true, then return value."""

        cycles_left = timeout_cycles

        while True:
            value = await self.read(address, timeout_cycles=timeout_cycles)
            if predicate(value):
                return value

            if cycles_left is not None:
                if cycles_left <= 0:
                    raise TimeoutError(f"Avalon-MM poll timeout at address {address}")
                cycles_left -= interval_cycles

            for _ in range(interval_cycles):
                await RisingEdge(self.clock)

    async def wait_set(self, address, mask, *, timeout_cycles=None):
        """Poll until all bits in mask are set."""

        mask = int(mask)
        return await self.poll(
            address,
            lambda value: (value & mask) == mask,
            timeout_cycles=timeout_cycles,
        )

    async def wait_clear(self, address, mask, *, timeout_cycles=None):
        """Poll until all bits in mask are clear."""

        mask = int(mask)
        return await self.poll(
            address,
            lambda value: (value & mask) == 0,
            timeout_cycles=timeout_cycles,
        )

    async def _start_access(self, address, data, byteenable, *, write, read):
        _drive(self.bus.address, address)
        _drive(self.bus.writedata, data)
        _drive(self.bus.write, write)
        _drive(self.bus.read, read)

        if self.bus.byteenable is not None:
            _drive(self.bus.byteenable, self._resolve_byteenable(byteenable))

    async def _wait_accepted(self, timeout_cycles):
        cycles = 0

        while True:
            await RisingEdge(self.clock)

            if self.bus.waitrequest is None or not _read_bool(self.bus.waitrequest):
                return

            cycles += 1
            if timeout_cycles is not None and cycles >= timeout_cycles:
                self._end_access()
                raise TimeoutError("Avalon-MM access waitrequest timeout")

    async def _wait_readdatavalid(self, timeout_cycles):
        cycles = 0

        while True:
            await RisingEdge(self.clock)

            if _read_bool(self.bus.readdatavalid):
                return

            cycles += 1
            if timeout_cycles is not None and cycles >= timeout_cycles:
                raise TimeoutError("Avalon-MM read readdatavalid timeout")

    def _end_access(self):
        _drive(self.bus.write, 0)
        _drive(self.bus.read, 0)

    def _resolve_byteenable(self, byteenable):
        if self.bus.byteenable is None:
            return 0

        width = self.bus.byteenable_width
        if byteenable is not None:
            return _check_width("byteenable", byteenable, width)
        if self.default_byteenable is not None:
            return _check_width("default_byteenable", self.default_byteenable, width)
        return _mask(width)

    def _validate_address(self, address):
        return _check_width("address", address, self.bus.address_width)

    def _validate_data(self, data):
        return _check_width("data", data, self.bus.data_width)


__all__ = [
    "AvalonMMBus",
    "AvalonMMMasterBFM",
]
