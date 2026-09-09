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

"""Cocotb model for Intel read and write DMA Avalon-ST interfaces."""

from dataclasses import dataclass
import logging

import cocotb
from cocotb.queue import Queue
from cocotb.triggers import ClockCycles
from cocotb.utils import get_sim_time

from cocotbext.avalon import (
    AvalonFormat,
    AvalonSTBus,
    AvalonSTFrame,
    AvalonSTMonitor,
    AvalonSTSink,
    AvalonSTSource,
)

__all__ = [
    "DMAAddressRegion",
    "IntelDMABFM",
    "IntelDMACommandMonitor",
    "ReadDMADescriptor",
    "SparseByteMemory",
    "WriteDMADescriptor",
]


def _avalon_st_label(bus):
    entity = getattr(bus, "_entity", None)
    entity_name = getattr(entity, "_name", None)
    bus_name = getattr(bus, "_name", None)

    if entity_name and bus_name:
        return f"{entity_name}.{bus_name}"
    if entity_name:
        return str(entity_name)
    if bus_name:
        return str(bus_name)
    return "avalon_st"


class SparseByteMemory:
    """Byte-addressed memory shared by the read and write DMA models."""

    def __init__(self):
        self._data = {}

    def write(self, address, data):
        for offset, value in enumerate(data):
            self._data[address + offset] = int(value) & 0xFF

    def read(self, address, length):
        return bytes(self._data.get(address + offset, 0) for offset in range(length))


@dataclass(frozen=True)
class ReadDMADescriptor:
    address: int
    length: int
    channel: int
    generate_sop: bool
    generate_eop: bool
    stop: bool
    reset: bool

    @classmethod
    def decode(cls, value):
        return cls(
            address=(value & 0xFFFFFFFF) | (((value >> 109) & 0xFFFFFFFF) << 32),
            length=(value >> 32) & 0xFFFFFFFF,
            channel=(value >> 64) & 0xFF,
            generate_sop=bool((value >> 72) & 1),
            generate_eop=bool((value >> 73) & 1),
            stop=bool((value >> 74) & 1),
            reset=bool((value >> 75) & 1),
        )


@dataclass(frozen=True)
class WriteDMADescriptor:
    address: int
    length: int
    end_on_eop: bool
    stop: bool
    reset: bool

    @classmethod
    def decode(cls, value):
        return cls(
            address=(value & 0xFFFFFFFF) | (((value >> 92) & 0xFFFFFFFF) << 32),
            length=(value >> 32) & 0xFFFFFFFF,
            end_on_eop=bool((value >> 64) & 1),
            stop=bool((value >> 66) & 1),
            reset=bool((value >> 67) & 1),
        )


@dataclass(frozen=True)
class DMAAddressRegion:
    """Allowed DMA address interval.

    ``end`` is exclusive, so ``start=0x1000, size=0x100`` covers
    ``0x1000..0x1100``.
    """

    name: str
    start: int
    size: int

    def __post_init__(self):
        if self.size < 0:
            raise ValueError("DMA address region size must be non-negative")

    @property
    def end(self):
        return self.start + self.size

    def contains(self, address, length):
        return length >= 0 and self.start <= address and address + length <= self.end

    def __str__(self):
        return f"{self.name}[0x{self.start:X}..0x{self.end:X})"


class IntelDMACommandMonitor:
    """Passive monitor for Intel read/write DMA descriptor streams.

    If address regions are provided, every non-control descriptor is checked
    immediately when it appears on the command stream.
    """

    def __init__(
        self,
        clock,
        reset=None,
        rdma_cmd_bus=None,
        wdma_cmd_bus=None,
        rdma_cmd_monitor=None,
        wdma_cmd_monitor=None,
        read_address_regions=None,
        write_address_regions=None,
        logger=None,
    ):
        self.read_address_regions = (
            None if read_address_regions is None else list(read_address_regions)
        )
        self.write_address_regions = (
            None if write_address_regions is None else list(write_address_regions)
        )
        self.read_descriptors = []
        self.write_descriptors = []
        self._tasks = []
        self.log = logger or logging.getLogger("cocotb.intel_dma_command_monitor")

        self.rdma_cmd_monitor = rdma_cmd_monitor or self._make_control_monitor(
            rdma_cmd_bus,
            clock,
            reset,
        )
        self.wdma_cmd_monitor = wdma_cmd_monitor or self._make_control_monitor(
            wdma_cmd_bus,
            clock,
            reset,
        )
        self._owns_rdma_cmd_monitor = rdma_cmd_monitor is None
        self._owns_wdma_cmd_monitor = wdma_cmd_monitor is None

    def _make_control_monitor(self, bus, clock, reset):
        if bus is None:
            return None

        fmt = AvalonFormat(bits_per_symbol=len(bus.data), symbols_per_beat=1)
        return AvalonSTMonitor(bus, fmt, clock, reset=reset, packets=False)

    def start(self):
        if self._tasks:
            return self

        if self.rdma_cmd_monitor is not None:
            self._tasks.append(cocotb.start_soon(self._run_read_commands()))
        if self.wdma_cmd_monitor is not None:
            self._tasks.append(cocotb.start_soon(self._run_write_commands()))

        return self

    def stop(self):
        for task in self._tasks:
            task.cancel()
        self._tasks = []

        if self._owns_rdma_cmd_monitor and self.rdma_cmd_monitor is not None:
            self.rdma_cmd_monitor.cancel()
        if self._owns_wdma_cmd_monitor and self.wdma_cmd_monitor is not None:
            self.wdma_cmd_monitor.cancel()

    async def _run_read_commands(self):
        while True:
            beat = await self.rdma_cmd_monitor.recv_beat()
            descriptor = ReadDMADescriptor.decode(beat.data)
            self.read_descriptors.append(descriptor)
            self._check_descriptor(
                "RDMA",
                descriptor,
                self.read_address_regions,
                self._monitor_label(self.rdma_cmd_monitor, "rdma_cmd"),
                beat.sim_time,
            )
            self.log.debug(
                "RDMA command address=0x%X length=%d channel=%d",
                descriptor.address,
                descriptor.length,
                descriptor.channel,
            )

    async def _run_write_commands(self):
        while True:
            beat = await self.wdma_cmd_monitor.recv_beat()
            descriptor = WriteDMADescriptor.decode(beat.data)
            self.write_descriptors.append(descriptor)
            self._check_descriptor(
                "WDMA",
                descriptor,
                self.write_address_regions,
                self._monitor_label(self.wdma_cmd_monitor, "wdma_cmd"),
                beat.sim_time,
            )
            self.log.debug(
                "WDMA command address=0x%X length=%d",
                descriptor.address,
                descriptor.length,
            )

    def _check_descriptor(
        self,
        name,
        descriptor,
        regions,
        interface_label=None,
        sim_time=None,
    ):
        if regions is None:
            return

        if descriptor.reset or descriptor.stop or descriptor.length == 0:
            return

        if any(region.contains(descriptor.address, descriptor.length) for region in regions):
            return

        where = interface_label or name
        when = "unknown" if sim_time is None else f"{sim_time} ps"
        raise AssertionError(
            f"{where}: {name} descriptor outside allowed regions at {when}: "
            f"address=0x{descriptor.address:X}, length={descriptor.length}, "
            f"allowed={self._format_regions(regions)}"
        )

    def _monitor_label(self, monitor, fallback):
        if monitor is not None and hasattr(monitor, "_bus_label"):
            return monitor._bus_label()
        return fallback

    def _format_regions(self, regions):
        return ", ".join(str(region) for region in regions)


class IntelDMABFM:
    """Avalon-ST stand-in for Intel read and write DMA components.

    A read descriptor queues memory contents on ``din`` and schedules a
    successful ``rdma_resp`` independently of data consumption. This models a
    read DMA whose internal FIFO can already contain data while the DUT stalls.

    A write descriptor consumes its byte count from ``dout``. Once all stream
    data has entered the model, it is committed to memory and a successful
    ``wdma_resp`` is scheduled after the configured completion delay.

    ``mode`` selects which side is modeled:

    * ``"full"`` models both read and write DMA interfaces.
    * ``"read"`` or ``"read_only"`` models only ``rdma_cmd``, ``rdma_resp``,
      and ``din``.
    * ``"write"`` or ``"write_only"`` models only ``wdma_cmd``,
      ``wdma_resp``, and ``dout``.

    Tests can set ``din_source.pause`` to delay read data presentation and
    ``dout_sink.pause`` to deassert ``dout_ready`` while write data waits.
    """

    READ_RESPONSE_DONE = 0b1100
    WRITE_RESPONSE_DONE_SHIFT = 43

    def __init__(
        self,
        dut,
        clock,
        reset,
        memory=None,
        read_response_delay_cycles=2,
        write_response_delay_cycles=2,
        rdma_cmd_bus=None,
        rdma_resp_bus=None,
        wdma_cmd_bus=None,
        wdma_resp_bus=None,
        din_bus=None,
        dout_bus=None,
        mode="full",
    ):
        if read_response_delay_cycles < 0 or write_response_delay_cycles < 0:
            raise ValueError("DMA response delays must be non-negative")

        self.enable_read, self.enable_write = self._decode_mode(mode)
        self.log = logging.getLogger(f"cocotb.{dut._name}.intel_dma_bfm")
        self.dut = dut
        self.clock = clock
        self.reset = reset
        self.memory = memory if memory is not None else SparseByteMemory()
        self.read_response_delay_cycles = read_response_delay_cycles
        self.write_response_delay_cycles = write_response_delay_cycles

        self.read_commands = Queue()
        self.write_commands = Queue()
        self.read_responses = Queue()
        self.write_responses = Queue()
        self._tasks = []

        self.rdma_cmd_sink = None
        self.rdma_resp_source = None
        self.wdma_cmd_sink = None
        self.wdma_resp_source = None
        self.din_source = None
        self.dout_sink = None
        self.read_data_bytes_per_beat = None
        self.write_data_bytes_per_beat = None

        if self.enable_read:
            self.rdma_cmd_sink = self._make_control_sink("rdma_cmd", rdma_cmd_bus)
            self.rdma_resp_source = self._make_control_source("rdma_resp", rdma_resp_bus)
            din_bus = din_bus if din_bus is not None else AvalonSTBus.from_prefix(dut, "din")
            self.din_source = AvalonSTSource(
                din_bus,
                self._make_byte_stream_format(din_bus),
                self.clock,
                reset=self.reset,
                packets=True,
                idle_value=0,
            )
            self.read_data_bytes_per_beat = self.din_source.symbols_per_beat

        if self.enable_write:
            self.wdma_cmd_sink = self._make_control_sink("wdma_cmd", wdma_cmd_bus)
            self.wdma_resp_source = self._make_control_source("wdma_resp", wdma_resp_bus)
            dout_bus = dout_bus if dout_bus is not None else AvalonSTBus.from_prefix(dut, "dout")
            self.dout_sink = AvalonSTSink(
                dout_bus,
                self._make_byte_stream_format(dout_bus),
                self.clock,
                reset=self.reset,
                packets=False,
            )
            self.write_data_bytes_per_beat = self.dout_sink.symbols_per_beat

        self.data_bytes_per_beat = (
            self.read_data_bytes_per_beat
            if self.read_data_bytes_per_beat is not None
            else self.write_data_bytes_per_beat
        )
        self.log.info(
            "Created DMA BFM: mode=%s, read_beat=%s bytes, write_beat=%s bytes, "
            "read_response_delay=%d cycles, write_response_delay=%d cycles, "
            "transaction_level=%s",
            mode,
            self.read_data_bytes_per_beat,
            self.write_data_bytes_per_beat,
            self.read_response_delay_cycles,
            self.write_response_delay_cycles,
            logging.INFO,
        )

    def _make_byte_stream_format(self, bus):
        data_width = len(bus.data)
        if data_width % 8:
            raise ValueError(
                f"{_avalon_st_label(bus)}: DMA data bus width must be byte-aligned"
            )
        return AvalonFormat(
            bits_per_symbol=8,
            symbols_per_beat=data_width // 8,
            first_symbol_in_high_order_bits=True,
        )

    def _decode_mode(self, mode):
        normalized = str(mode).lower().replace("-", "_").replace(" ", "_")

        if normalized in ("full", "read_write", "readwrite"):
            return True, True
        if normalized in ("read", "read_only", "readonly"):
            return True, False
        if normalized in ("write", "write_only", "writeonly"):
            return False, True

        raise ValueError(
            "IntelDMABFM mode must be 'full', 'read', 'read_only', "
            "'write', or 'write_only'"
        )

    def _log_transaction(self, message, *args):
        self.log.log(logging.DEBUG, message, *args)

    def _make_control_sink(self, prefix, bus=None):
        if bus is None:
            bus = AvalonSTBus.from_prefix(self.dut, prefix)

        fmt = AvalonFormat(bits_per_symbol=len(bus.data), symbols_per_beat=1)
        return AvalonSTSink(bus, fmt, self.clock, reset=self.reset, packets=False)

    def _make_control_source(self, prefix, bus=None):
        if bus is None:
            bus = AvalonSTBus.from_prefix(self.dut, prefix)

        fmt = AvalonFormat(bits_per_symbol=len(bus.data), symbols_per_beat=1)
        return AvalonSTSource(
            bus,
            fmt,
            self.clock,
            reset=self.reset,
            packets=False,
            idle_value=0,
        )

    def start(self):
        if not self._tasks:
            if self.enable_read:
                self._tasks.append(cocotb.start_soon(self._run_reads()))
            if self.enable_write:
                self._tasks.append(cocotb.start_soon(self._run_writes()))
        return self

    def stop(self):
        for task in self._tasks:
            task.cancel()
        self._tasks = []

        for bfm in (
            self.rdma_cmd_sink,
            self.rdma_resp_source,
            self.wdma_cmd_sink,
            self.wdma_resp_source,
            self.din_source,
            self.dout_sink,
        ):
            if bfm is not None:
                bfm.cancel()

    async def _run_reads(self):
        while True:
            descriptor = ReadDMADescriptor.decode((await self.rdma_cmd_sink.recv_beat()).data)
            await self.read_commands.put(descriptor)
            self._log_transaction(
                "READ command: address=0x%016x length=%d channel=%d sop=%d eop=%d",
                descriptor.address,
                descriptor.length,
                descriptor.channel,
                descriptor.generate_sop,
                descriptor.generate_eop,
            )

            if descriptor.reset:
                response = 0b0001
            elif descriptor.stop:
                response = 0b0010
            else:
                response = self.READ_RESPONSE_DONE
                if descriptor.length:
                    if descriptor.length % self.read_data_bytes_per_beat:
                        raise RuntimeError(
                            f"{self.din_source._bus_label()}: Read DMA BFM requires "
                            "transfers aligned to the exported din beat because the "
                            "component does not expose din_empty; "
                            f"address=0x{descriptor.address:016X}, "
                            f"length={descriptor.length}, time={get_sim_time()} ps"
                        )
                    if not descriptor.generate_sop or not descriptor.generate_eop:
                        raise RuntimeError(
                            f"{self.din_source._bus_label()}: Read DMA BFM expects "
                            "packetized read descriptors; "
                            f"address=0x{descriptor.address:016X}, "
                            f"length={descriptor.length}, time={get_sim_time()} ps"
                        )

                    await self.din_source.send(
                        AvalonSTFrame(
                            self.memory.read(descriptor.address, descriptor.length),
                            channel=descriptor.channel,
                        )
                    )
                    self._log_transaction(
                        "READ data queued: address=0x%016x length=%d channel=%d",
                        descriptor.address,
                        descriptor.length,
                        descriptor.channel,
                    )

            cocotb.start_soon(self._issue_read_response(descriptor, response))

    async def _issue_read_response(self, descriptor, response):
        await ClockCycles(self.clock, self.read_response_delay_cycles)
        await self.rdma_resp_source.send(AvalonSTFrame([response]))
        await self.read_responses.put(descriptor)
        self._log_transaction(
            "READ response queued: address=0x%016x response=0x%x",
            descriptor.address,
            response,
        )

    async def _run_writes(self):
        while True:
            descriptor = WriteDMADescriptor.decode((await self.wdma_cmd_sink.recv_beat()).data)
            await self.write_commands.put(descriptor)
            self._log_transaction(
                "WRITE command: address=0x%016x length=%d end_on_eop=%d",
                descriptor.address,
                descriptor.length,
                descriptor.end_on_eop,
            )

            if descriptor.reset:
                response = 0b10 << 32
            elif descriptor.stop:
                response = 0b100 << 32
            else:
                payload = await self._receive_write_payload(descriptor.length)
                await ClockCycles(self.clock, self.write_response_delay_cycles)
                self.memory.write(descriptor.address, payload)
                response = (1 << self.WRITE_RESPONSE_DONE_SHIFT) | descriptor.length
                self._log_transaction(
                    "WRITE data stored: address=0x%016x length=%d",
                    descriptor.address,
                    len(payload),
                )

            await self.wdma_resp_source.send(AvalonSTFrame([response]))
            await self.write_responses.put(descriptor)
            self._log_transaction(
                "WRITE response queued: address=0x%016x response=0x%x",
                descriptor.address,
                response,
            )

    async def _receive_write_payload(self, length):
        payload = bytearray()
        beats_needed = (
            length + self.write_data_bytes_per_beat - 1
        ) // self.write_data_bytes_per_beat

        for _ in range(beats_needed):
            payload.extend((await self.dout_sink.recv_beat()).symbols)

        return bytes(payload[:length])
