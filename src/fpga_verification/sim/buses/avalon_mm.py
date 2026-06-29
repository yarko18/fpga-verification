# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""Reusable Avalon-MM cocotb bus helpers and BFMs."""

from collections import deque
from dataclasses import dataclass
import logging
from typing import Callable

import cocotb
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
    if signal is not None:
        signal.value = int(value)


def _read_int(signal, name, default=None):
    if signal is None:
        if default is not None:
            return default
        raise RuntimeError(f"Avalon-MM signal {name} is not present")

    try:
        return int(signal.value)
    except ValueError as exc:
        if default is not None:
            return default
        raise RuntimeError(f"Avalon-MM signal {name} is X/Z") from exc


def _read_bool(signal, name, default=False):
    return bool(_read_int(signal, name, int(default)))


@dataclass
class AvalonMMBus:
    """Signal bundle for Avalon-MM BFMs.

    ``address`` is the only required signal.  All transfer signals are optional
    so read-only and write-only master ports can be bound with the same helper.
    Standard ``<prefix>_<signal>`` names are used by :meth:`from_prefix`.
    """

    address: object
    writedata: object = None
    write: object = None
    read: object = None
    readdata: object = None
    waitrequest: object = None
    readdatavalid: object = None
    byteenable: object = None
    burstcount: object = None
    beginbursttransfer: object = None
    response: object = None
    writeresponsevalid: object = None
    lock: object = None
    debugaccess: object = None

    @classmethod
    def from_prefix(cls, entity, prefix):
        """Build a bus from signals named '<prefix>_<signal>' on entity."""

        def required(name):
            return getattr(entity, f"{prefix}_{name}")

        def optional(name):
            return getattr(entity, f"{prefix}_{name}", None)

        return cls(
            address=required("address"),
            writedata=optional("writedata"),
            write=optional("write"),
            read=optional("read"),
            readdata=optional("readdata"),
            waitrequest=optional("waitrequest"),
            readdatavalid=optional("readdatavalid"),
            byteenable=optional("byteenable"),
            burstcount=optional("burstcount"),
            beginbursttransfer=optional("beginbursttransfer"),
            response=optional("response"),
            writeresponsevalid=optional("writeresponsevalid"),
            lock=optional("lock"),
            debugaccess=optional("debugaccess"),
        )

    @property
    def address_width(self):
        return _signal_width(self.address)

    @property
    def write_data_width(self):
        if self.writedata is None:
            return None
        return _signal_width(self.writedata)

    @property
    def read_data_width(self):
        if self.readdata is None:
            return None
        return _signal_width(self.readdata)

    @property
    def data_width(self):
        if self.writedata is not None:
            return self.write_data_width
        if self.readdata is not None:
            return self.read_data_width
        raise ValueError("Avalon-MM bus has neither writedata nor readdata")

    @property
    def byteenable_width(self):
        if self.byteenable is not None:
            return _signal_width(self.byteenable)
        return self.data_width // 8

    @property
    def burstcount_width(self):
        if self.burstcount is None:
            return 0
        return _signal_width(self.burstcount)

    @property
    def has_read(self):
        return self.read is not None

    @property
    def has_write(self):
        return self.write is not None


@dataclass(frozen=True)
class AvalonMMTransaction:
    """Observed Avalon-MM memory-side transfer beat."""

    kind: str
    address: int
    data: int | None
    byteenable: int
    burstcount: int
    beat_index: int


class AvalonMMMasterBFM:
    """Simple Avalon-MM host/master BFM.

    The BFM supports single-beat read/write transactions with optional
    waitrequest, readdatavalid, byteenable, and burstcount signals. It
    intentionally stays below UVM level so tests can use it directly or wrap it
    in a pyuvm driver later.
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

    def start(self):
        """Drive the master outputs to an idle state."""

        _drive(self.bus.address, 0)
        _drive(self.bus.writedata, 0)
        _drive(self.bus.write, 0)
        _drive(self.bus.read, 0)
        _drive(self.bus.beginbursttransfer, 0)
        _drive(self.bus.lock, 0)
        _drive(self.bus.debugaccess, 0)

        if self.bus.byteenable is not None:
            _drive(self.bus.byteenable, self._resolve_byteenable(None))
        if self.bus.burstcount is not None:
            _drive(self.bus.burstcount, 1)

    async def wait_reset_release(self, active_value=1):
        """Wait until reset is not asserted, if a reset signal was provided."""

        if self.reset is None:
            return

        while int(self.reset.value) == int(active_value):
            await RisingEdge(self.clock)

    async def write(self, address, data, byteenable=None, timeout_cycles=None):
        """Issue one Avalon-MM write and return after it is accepted."""

        self._require_write()
        self._validate_address(address)
        self._validate_write_data(data)

        await RisingEdge(self.clock)
        await self._start_access(address, data, byteenable, write=1, read=0)
        await self._wait_accepted(timeout_cycles)
        self._end_access()

    async def read(self, address, byteenable=None, timeout_cycles=None):
        """Issue one Avalon-MM read and return the sampled readdata value."""

        self._require_read()
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
        _drive(self.bus.beginbursttransfer, int(write or read))

        if self.bus.byteenable is not None:
            _drive(self.bus.byteenable, self._resolve_byteenable(byteenable))
        if self.bus.burstcount is not None:
            _drive(self.bus.burstcount, 1)

    async def _wait_accepted(self, timeout_cycles):
        cycles = 0

        while True:
            await RisingEdge(self.clock)

            if self.bus.waitrequest is None or not _read_bool(
                self.bus.waitrequest,
                "waitrequest",
            ):
                return

            cycles += 1
            if timeout_cycles is not None and cycles >= timeout_cycles:
                self._end_access()
                raise TimeoutError("Avalon-MM access waitrequest timeout")

    async def _wait_readdatavalid(self, timeout_cycles):
        cycles = 0

        while True:
            await RisingEdge(self.clock)

            if _read_bool(self.bus.readdatavalid, "readdatavalid"):
                return

            cycles += 1
            if timeout_cycles is not None and cycles >= timeout_cycles:
                raise TimeoutError("Avalon-MM read readdatavalid timeout")

    def _end_access(self):
        _drive(self.bus.write, 0)
        _drive(self.bus.read, 0)
        _drive(self.bus.beginbursttransfer, 0)

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

    def _validate_write_data(self, data):
        return _check_width("data", data, self.bus.write_data_width)

    def _require_read(self):
        if self.bus.read is None or self.bus.readdata is None:
            raise RuntimeError("Avalon-MM bus does not expose read/readdata")

    def _require_write(self):
        if self.bus.write is None or self.bus.writedata is None:
            raise RuntimeError("Avalon-MM bus does not expose write/writedata")


class AvalonMMSlaveBFM:
    """Avalon-MM slave BFM for memory-side IP master tests.

    The slave accepts read and/or write master ports.  It supports burstcount,
    byteenable, waitrequest backpressure, variable-latency read responses, and
    multiple queued in-order read responses.  Read and write data storage is
    delegated to ``read_word`` and ``write_word`` methods so subclasses can
    connect any backing store.
    """

    def __init__(
        self,
        bus,
        clock,
        reset=None,
        *,
        read_latency=1,
        reset_active_level=True,
        waitrequest_during_reset=True,
        idle_readdata=0,
        logger=None,
    ):
        self.bus = bus
        self.clock = clock
        self.reset = reset
        self.read_latency = int(read_latency)
        self.reset_active_level = bool(reset_active_level)
        self.waitrequest_during_reset = bool(waitrequest_during_reset)
        self.idle_readdata = int(idle_readdata)
        self.log = logger or logging.getLogger("cocotb.avalon_mm.slave")

        if self.read_latency < 0:
            raise ValueError("read_latency must be non-negative")
        if (
            self.bus.read_data_width is not None
            and self.bus.write_data_width is not None
            and self.bus.read_data_width != self.bus.write_data_width
        ):
            raise ValueError(
                "Avalon-MM read and write data widths differ "
                f"({self.bus.read_data_width} != {self.bus.write_data_width})"
            )
        if self.bus.data_width % 8:
            raise ValueError("Avalon-MM memory data width must be byte-aligned")
        if (
            self.bus.byteenable is not None
            and self.bus.byteenable_width != self.bus.data_width // 8
        ):
            raise ValueError(
                "Avalon-MM byteenable width must match data width in bytes "
                f"({self.bus.byteenable_width} != {self.bus.data_width // 8})"
            )
        if self.bus.has_read and self.bus.readdata is None:
            raise ValueError("read-capable Avalon-MM bus must expose readdata")
        if self.bus.has_write and self.bus.writedata is None:
            raise ValueError("write-capable Avalon-MM bus must expose writedata")

        self.word_bytes = self.bus.data_width // 8
        self._read_queue = deque()
        self._write_burst_address = 0
        self._write_burst_count = 0
        self._write_burst_index = 0
        self._write_burst_remaining = 0
        self._pause = False
        self._pause_generator = None
        self._task = None
        self._waitrequest_asserted = False

        self.read_transactions = []
        self.write_transactions = []

    @classmethod
    def from_prefix(cls, entity, prefix, clock, reset=None, **kwargs):
        return cls(AvalonMMBus.from_prefix(entity, prefix), clock, reset, **kwargs)

    @property
    def pause(self):
        return self._pause

    @pause.setter
    def pause(self, value):
        self._pause = bool(value)

    def set_pause_generator(self, generator=None):
        self._pause_generator = None if generator is None else iter(generator)

    def clear_pause_generator(self):
        self._pause_generator = None

    def init_idle(self):
        reset_active = self._reset_active()
        self._drive_waitrequest(reset_active and self.waitrequest_during_reset)
        _drive(self.bus.readdata, self.idle_readdata)
        _drive(self.bus.readdatavalid, 0)
        _drive(self.bus.response, 0)
        _drive(self.bus.writeresponsevalid, 0)

    def start(self):
        if self._task is None:
            self.init_idle()
            self._task = cocotb.start_soon(self._run())
        return self

    def stop(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def read_word(self, address, byteenable):
        """Return one data word for a read beat.

        Subclasses override this.  ``byteenable`` uses Avalon byte-lane bit
        numbering where bit 0 corresponds to the lowest addressed byte lane.
        """

        raise NotImplementedError()

    def write_word(self, address, data, byteenable):
        """Store one data word for a write beat."""

        raise NotImplementedError()

    async def _run(self):
        while True:
            await RisingEdge(self.clock)

            if self._reset_active():
                self._handle_reset()
                continue

            accepted = not self._waitrequest_asserted
            read = _read_bool(self.bus.read, "read", False)
            write = _read_bool(self.bus.write, "write", False)

            if read and write:
                raise RuntimeError("Avalon-MM read and write asserted together")

            if accepted and read:
                self._accept_read()
            if accepted and write:
                self._accept_write()

            self._drive_next_read_response()
            self._drive_waitrequest(self._next_waitrequest())

    def _handle_reset(self):
        self._read_queue.clear()
        self._write_burst_remaining = 0
        _drive(self.bus.readdatavalid, 0)
        _drive(self.bus.writeresponsevalid, 0)
        _drive(self.bus.readdata, self.idle_readdata)
        self._drive_waitrequest(self.waitrequest_during_reset)

    def _accept_read(self):
        burstcount = self._sample_burstcount()
        address = _read_int(self.bus.address, "address")
        byteenable = self._sample_byteenable()

        for beat_index in range(burstcount):
            beat_address = address + beat_index * self.word_bytes
            data = self.read_word(beat_address, byteenable)
            data = _check_width("readdata", data, self.bus.read_data_width)
            self._queue_read_data(data)
            self.read_transactions.append(
                AvalonMMTransaction(
                    "read",
                    beat_address,
                    None,
                    byteenable,
                    burstcount,
                    beat_index,
                )
            )

        self.log.debug(
            "READ address=0x%X burstcount=%d byteenable=0x%X",
            address,
            burstcount,
            byteenable,
        )

    def _accept_write(self):
        if self._write_burst_remaining == 0:
            self._write_burst_address = _read_int(self.bus.address, "address")
            self._write_burst_count = self._sample_burstcount()
            self._write_burst_index = 0
            self._write_burst_remaining = self._write_burst_count

        beat_index = self._write_burst_index
        beat_address = self._write_burst_address + beat_index * self.word_bytes
        byteenable = self._sample_byteenable()
        data = _read_int(self.bus.writedata, "writedata")

        self.write_word(beat_address, data, byteenable)
        self.write_transactions.append(
            AvalonMMTransaction(
                "write",
                beat_address,
                data,
                byteenable,
                self._write_burst_count,
                beat_index,
            )
        )

        self.log.debug(
            "WRITE address=0x%X data=0x%X burstcount=%d beat=%d byteenable=0x%X",
            beat_address,
            data,
            self._write_burst_count,
            beat_index,
            byteenable,
        )

        self._write_burst_index += 1
        self._write_burst_remaining -= 1

    def _queue_read_data(self, data):
        delay = self.read_latency if not self._read_queue else 1
        self._read_queue.append([delay, data])

    def _drive_next_read_response(self):
        if not self._read_queue:
            _drive(self.bus.readdatavalid, 0)
            _drive(self.bus.readdata, self.idle_readdata)
            return

        entry = self._read_queue[0]
        if entry[0] > 0:
            entry[0] -= 1

        if entry[0] <= 0:
            _, data = self._read_queue.popleft()
            _drive(self.bus.readdata, data)
            _drive(self.bus.readdatavalid, 1)
        else:
            _drive(self.bus.readdatavalid, 0)

    def _next_waitrequest(self):
        if self._pause_generator is not None:
            try:
                self.pause = next(self._pause_generator)
            except StopIteration:
                self._pause_generator = None

        return bool(self.pause)

    def _drive_waitrequest(self, value):
        self._waitrequest_asserted = bool(value)
        _drive(self.bus.waitrequest, int(self._waitrequest_asserted))

    def _sample_burstcount(self):
        if self.bus.burstcount is None:
            return 1

        burstcount = _read_int(self.bus.burstcount, "burstcount", 1)
        if burstcount <= 0:
            raise RuntimeError(f"Avalon-MM burstcount must be > 0, got {burstcount}")
        return burstcount

    def _sample_byteenable(self):
        if self.bus.byteenable is None:
            return _mask(self.bus.byteenable_width)

        return _check_width(
            "byteenable",
            _read_int(self.bus.byteenable, "byteenable"),
            self.bus.byteenable_width,
        )

    def _reset_active(self):
        if self.reset is None:
            return False
        return (
            _read_bool(self.reset, "reset", self.reset_active_level)
            == self.reset_active_level
        )


class AvalonMMMemoryBFM(AvalonMMSlaveBFM):
    """Avalon-MM slave backed by a byte-addressed memory object.

    The memory object must provide ``read(address, length) -> bytes`` and
    ``write(address, data)`` methods.  ``SparseByteMemory`` from
    ``fpga_verification.sim.bfms.intel_dma`` satisfies this contract.
    """

    def __init__(
        self,
        bus,
        clock,
        reset=None,
        *,
        memory,
        byteorder="little",
        **kwargs,
    ):
        if byteorder not in ("little", "big"):
            raise ValueError("byteorder must be 'little' or 'big'")

        self.memory = memory
        self.byteorder = byteorder
        super().__init__(bus, clock, reset, **kwargs)

    @classmethod
    def from_prefix(cls, entity, prefix, clock, reset=None, **kwargs):
        return cls(AvalonMMBus.from_prefix(entity, prefix), clock, reset, **kwargs)

    def read_word(self, address, byteenable):
        raw = bytearray(self.memory.read(address, self.word_bytes))

        if len(raw) != self.word_bytes:
            raise RuntimeError(
                f"memory.read(0x{address:X}, {self.word_bytes}) returned {len(raw)} bytes"
            )

        for lane in range(self.word_bytes):
            if not (byteenable & (1 << lane)):
                raw[lane] = 0

        return int.from_bytes(raw, self.byteorder)

    def write_word(self, address, data, byteenable):
        current = bytearray(self.memory.read(address, self.word_bytes))
        incoming = int(data).to_bytes(self.word_bytes, self.byteorder)

        if len(current) != self.word_bytes:
            raise RuntimeError(
                f"memory.read(0x{address:X}, {self.word_bytes}) returned "
                f"{len(current)} bytes"
            )

        for lane in range(self.word_bytes):
            if byteenable & (1 << lane):
                current[lane] = incoming[lane]

        self.memory.write(address, current)


__all__ = [
    "AvalonMMBus",
    "AvalonMMMasterBFM",
    "AvalonMMMemoryBFM",
    "AvalonMMSlaveBFM",
    "AvalonMMTransaction",
]
