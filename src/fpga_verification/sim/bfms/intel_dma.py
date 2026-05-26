# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""Cocotb model for Intel read and write DMA Avalon-ST interfaces."""

from dataclasses import dataclass
import logging

import cocotb
from cocotb.queue import Queue
from cocotb.triggers import ClockCycles

from fpga_verification.sim.buses import AvalonSTBus, AvalonSTFrame, AvalonSTSink, AvalonSTSource

__all__ = [
    "IntelDMABFM",
    "ReadDMADescriptor",
    "SparseByteMemory",
    "WriteDMADescriptor",
]


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


class IntelDMABFM:
    """Avalon-ST stand-in for Intel read and write DMA components.

    A read descriptor queues memory contents on ``din`` and schedules a
    successful ``rdma_resp`` independently of data consumption. This models a
    read DMA whose internal FIFO can already contain data while the DUT stalls.

    A write descriptor consumes its byte count from ``dout``. Once all stream
    data has entered the model, it is committed to memory and a successful
    ``wdma_resp`` is scheduled after the configured completion delay.

    Tests can set ``din_source.pause`` to delay read data presentation and
    ``dout_sink.pause`` to deassert ``dout_ready`` while write data waits.
    """

    READ_RESPONSE_DONE = 0b1100
    WRITE_RESPONSE_DONE_SHIFT = 43

    def __init__(
        self,
        dut,
        memory=None,
        read_response_delay_cycles=2,
        write_response_delay_cycles=2,
    ):
        if read_response_delay_cycles < 0 or write_response_delay_cycles < 0:
            raise ValueError("DMA response delays must be non-negative")

        self.log = logging.getLogger(f"cocotb.{dut._name}.intel_dma_bfm")
        self.dut = dut
        self.clock = dut.mem_clk
        self.reset = dut.mem_reset
        self.memory = memory if memory is not None else SparseByteMemory()
        self.read_response_delay_cycles = read_response_delay_cycles
        self.write_response_delay_cycles = write_response_delay_cycles

        self.read_commands = Queue()
        self.write_commands = Queue()
        self.read_responses = Queue()
        self.write_responses = Queue()
        self._tasks = []

        self.rdma_cmd_sink = self._make_control_sink("rdma_cmd")
        self.rdma_resp_source = self._make_control_source("rdma_resp")
        self.wdma_cmd_sink = self._make_control_sink("wdma_cmd")
        self.wdma_resp_source = self._make_control_source("wdma_resp")

        self.din_source = AvalonSTSource(
            AvalonSTBus.from_prefix(dut, "din"),
            self.clock,
            reset=self.reset,
            data_bits_per_symbol=8,
            first_symbol_in_high_order_bits=True,
            packets=True,
            idle_value=0,
        )
        self.dout_sink = AvalonSTSink(
            AvalonSTBus.from_prefix(dut, "dout"),
            self.clock,
            reset=self.reset,
            data_bits_per_symbol=8,
            first_symbol_in_high_order_bits=True,
            packets=False,
        )

        self.data_bytes_per_beat = self.din_source.symbols_per_beat
        self.log.info(
            "Created DMA BFM: beat=%d bytes, read_response_delay=%d cycles, "
            "write_response_delay=%d cycles, transaction_level=%s",
            self.data_bytes_per_beat,
            self.read_response_delay_cycles,
            self.write_response_delay_cycles,
            logging.INFO,
        )

    def _log_transaction(self, message, *args):
        self.log.log(logging.DEBUG, message, *args)

    def _make_control_sink(self, prefix):
        bus = AvalonSTBus.from_prefix(self.dut, prefix)
        return AvalonSTSink(
            bus,
            self.clock,
            reset=self.reset,
            data_bits_per_symbol=len(bus.data),
            symbols_per_beat=1,
            packets=False,
        )

    def _make_control_source(self, prefix):
        bus = AvalonSTBus.from_prefix(self.dut, prefix)
        return AvalonSTSource(
            bus,
            self.clock,
            reset=self.reset,
            data_bits_per_symbol=len(bus.data),
            symbols_per_beat=1,
            packets=False,
            idle_value=0,
        )

    def start(self):
        if not self._tasks:
            self._tasks = [
                cocotb.start_soon(self._run_reads()),
                cocotb.start_soon(self._run_writes()),
            ]
        return self

    def stop(self):
        for task in self._tasks:
            task.cancel()
        self._tasks = []

        self.rdma_cmd_sink.cancel()
        self.rdma_resp_source.cancel()
        self.wdma_cmd_sink.cancel()
        self.wdma_resp_source.cancel()
        self.din_source.cancel()
        self.dout_sink.cancel()

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
                    if descriptor.length % self.data_bytes_per_beat:
                        raise RuntimeError(
                            "Read DMA BFM requires transfers aligned to the exported "
                            "din beat because the component does not expose din_empty"
                        )
                    if not descriptor.generate_sop or not descriptor.generate_eop:
                        raise RuntimeError("Read DMA BFM expects packetized read descriptors")

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
        beats_needed = (length + self.data_bytes_per_beat - 1) // self.data_bytes_per_beat

        for _ in range(beats_needed):
            payload.extend((await self.dout_sink.recv_beat()).symbols)

        return bytes(payload[:length])
