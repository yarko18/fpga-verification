# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""Intel Avalon-ST Video pyuvm agent."""

from random import random

import cocotb
from cocotb.triggers import Edge, Event
from pyuvm import (
    uvm_active_passive_enum,
    uvm_agent,
    uvm_analysis_port,
    uvm_driver,
    uvm_monitor,
    uvm_sequence,
    uvm_sequence_item,
    uvm_sequencer,
)

from fpga_verification.protocols.avalon_st.intel_video import (
    VIPPacket,
    VIPProtocolChecker,
    vip_packet_from_symbols,
)
from fpga_verification.sim.buses import (
    AvalonSTFrame,
    AvalonSTMonitor,
    AvalonSTSink,
    AvalonSTSource,
)
from fpga_verification.video import VideoFormat


def _random_pause_generator():
    while True:
        yield random() < 0.25


def _validate_vip_bus(bus, name, fmt):
    data_width = len(bus.data)
    if data_width != fmt.payload_width:
        raise ValueError(
            f"{name} data width must be {fmt.payload_width} bits, "
            f"got {data_width}"
        )


def _bfm_kwargs(reset_active_level, ready_latency=0, ready_allowance=None):
    return {
        "reset_active_level": reset_active_level,
        "ready_latency": ready_latency,
        "ready_allowance": ready_allowance,
        "packets": True,
    }


def _make_vip_monitor(
    bus,
    clock,
    reset,
    fmt,
    reset_active_level,
    ready_latency=0,
    ready_allowance=None,
):
    _validate_vip_bus(bus, "VIP bus", fmt)
    return AvalonSTMonitor(
        bus,
        fmt,
        clock,
        reset=reset,
        **_bfm_kwargs(reset_active_level, ready_latency, ready_allowance),
    )


def _make_vip_source(
    bus,
    clock,
    reset,
    fmt,
    reset_active_level,
    ready_latency=0,
    ready_allowance=None,
    idle_value=0,
):
    _validate_vip_bus(bus, "VIP source bus", fmt)
    return AvalonSTSource(
        bus,
        fmt,
        clock,
        reset=reset,
        idle_value=idle_value,
        **_bfm_kwargs(reset_active_level, ready_latency, ready_allowance),
    )


def _make_vip_sink(
    bus,
    clock,
    reset,
    fmt,
    reset_active_level,
    ready_latency=0,
    ready_allowance=None,
):
    _validate_vip_bus(bus, "VIP sink bus", fmt)
    return AvalonSTSink(
        bus,
        fmt,
        clock,
        reset=reset,
        **_bfm_kwargs(reset_active_level, ready_latency, ready_allowance),
    )


class VIPItem(uvm_sequence_item):
    """Sequence item containing one complete Intel VIP packet."""

    def __init__(self, packet, name="vip_item"):
        super().__init__(name)
        if not isinstance(packet, VIPPacket):
            raise TypeError("packet must be a VIPPacket")
        self.packet = packet

    def to_vip_packet(self):
        return self.packet

    @classmethod
    def from_packet(cls, packet, name="vip_item"):
        return cls(packet, name=name)


class VIPDriver(uvm_driver):
    """Drive VIP packet sequence items onto an Avalon-ST source."""

    def __init__(self, name, parent, source, fmt):
        super().__init__(name, parent)
        self.source = source
        self.fmt = fmt

    async def run_phase(self):
        while True:
            item = await self.seq_item_port.get_next_item()
            try:
                await self._send_item(item)
            finally:
                self.seq_item_port.item_done()

    async def _send_item(self, item):
        if not isinstance(item, VIPItem):
            raise TypeError("VIPDriver accepts VIPItem instances")

        tx_complete = Event()
        packet = item.to_vip_packet()

        def log_completed_frame(frame):
            self.source.log.debug("TX VIP packet: %s", frame)
            tx_complete.set()

        frame = AvalonSTFrame(
            packet.to_symbols(self.fmt.samples_per_beat),
            tx_complete=log_completed_frame,
        )
        await self.source.send(frame)
        await tx_complete.wait()


class VIPMonitor(uvm_monitor):
    """Observe VIP packets, validate stream protocol, and publish packets."""

    def __init__(
        self,
        name,
        parent,
        bus,
        clock,
        fmt,
        reset=None,
        reset_active_level=True,
        ready_latency=0,
        ready_allowance=None,
        drive_ready=False,
        randomize=False,
    ):
        super().__init__(name, parent)
        if not isinstance(fmt, VideoFormat):
            raise TypeError("fmt must be a VideoFormat")
        self.bus = bus
        self.clock = clock
        self.reset = reset
        self.reset_active_level = bool(reset_active_level)
        self.ready_latency = ready_latency
        self.ready_allowance = ready_allowance
        self.fmt = fmt
        self.drive_ready = drive_ready
        self.randomize = randomize
        self.monitor = None
        self.protocol_checker = VIPProtocolChecker(fmt)
        self.analysis_port = uvm_analysis_port("analysis_port", self)

    def build_phase(self):
        super().build_phase()
        if self.drive_ready:
            self.monitor = _make_vip_sink(
                self.bus,
                self.clock,
                self.reset,
                self.fmt,
                self.reset_active_level,
                self.ready_latency,
                self.ready_allowance,
            )
            if self.randomize:
                self.monitor.set_pause_generator(_random_pause_generator())
        else:
            self.monitor = _make_vip_monitor(
                self.bus,
                self.clock,
                self.reset,
                self.fmt,
                self.reset_active_level,
                self.ready_latency,
                self.ready_allowance,
            )

    async def recv_packet(self):
        frame = await self.monitor.recv()
        self.monitor.log.debug("RX VIP packet: %s", frame)
        packet = vip_packet_from_symbols(
            frame.data,
            symbols_per_beat=self.fmt.samples_per_beat,
        )
        self.protocol_checker.observe(packet)
        return packet

    async def _watch_reset(self):
        while True:
            try:
                trigger = self.reset.value_change
            except AttributeError:
                trigger = Edge(self.reset)
            await trigger
            try:
                level = bool(int(self.reset.value))
            except ValueError:
                level = self.reset_active_level
            if level == self.reset_active_level:
                self.reset_protocol_state()

    async def run_phase(self):
        reset_task = None
        if self.reset is not None:
            reset_task = cocotb.start_soon(self._watch_reset())
        try:
            while True:
                self.analysis_port.write(await self.recv_packet())
        finally:
            if reset_task is not None:
                reset_task.cancel()

    def reset_protocol_state(self):
        self.protocol_checker.reset()


class VIPAgent(uvm_agent):
    """Source/sink pyuvm agent for Intel Avalon-ST Video packet streams."""

    def __init__(
        self,
        name,
        parent,
        clock,
        reset,
        source_bus=None,
        sink_bus=None,
        source_fmt=None,
        sink_fmt=None,
        reset_active_level=True,
        ready_latency=0,
        ready_allowance=None,
        idle_value=0,
        randomize=False,
        is_active=uvm_active_passive_enum.UVM_ACTIVE,
    ):
        super().__init__(name, parent)
        if source_bus is None and sink_bus is None:
            raise ValueError("VIPAgent requires source_bus, sink_bus, or both")

        if sink_fmt is None:
            sink_fmt = source_fmt
        if source_bus is not None and source_fmt is None:
            raise ValueError("source_fmt is required when source_bus is used")
        if sink_bus is not None and sink_fmt is None:
            raise ValueError("sink_fmt is required when sink_bus is used")
        if source_fmt is not None and not isinstance(source_fmt, VideoFormat):
            raise TypeError("source_fmt must be a VideoFormat")
        if sink_fmt is not None and not isinstance(sink_fmt, VideoFormat):
            raise TypeError("sink_fmt must be a VideoFormat")

        self.clock = clock
        self.reset = reset
        self.reset_active_level = bool(reset_active_level)
        self.ready_latency = ready_latency
        self.ready_allowance = ready_allowance
        self.idle_value = idle_value
        self.source_bus = source_bus
        self.source_fmt = source_fmt
        self.sink_bus = sink_bus
        self.sink_fmt = sink_fmt
        self.randomize = randomize
        self._requested_is_active = is_active

        self.sequencer = None
        self.source = None
        self.source_driver = None
        self.source_monitor = None
        self.sink_monitor = None

    def build_phase(self):
        super().build_phase()
        self.is_active = self._requested_is_active

        if self.source_bus is not None:
            self.source_monitor = VIPMonitor(
                "source_monitor",
                self,
                self.source_bus,
                self.clock,
                self.source_fmt,
                self.reset,
                self.reset_active_level,
                self.ready_latency,
                self.ready_allowance,
            )

        if self.sink_bus is not None:
            self.sink_monitor = VIPMonitor(
                "sink_monitor",
                self,
                self.sink_bus,
                self.clock,
                self.sink_fmt,
                self.reset,
                self.reset_active_level,
                self.ready_latency,
                self.ready_allowance,
                drive_ready=self.active(),
                randomize=self.randomize,
            )

        if self.active() and self.source_bus is not None:
            self.source = _make_vip_source(
                self.source_bus,
                self.clock,
                self.reset,
                self.source_fmt,
                self.reset_active_level,
                self.ready_latency,
                self.ready_allowance,
                self.idle_value,
            )
            if self.randomize:
                self.source.set_pause_generator(_random_pause_generator())
            self.sequencer = uvm_sequencer("sequencer", self)
            self.source_driver = VIPDriver(
                "source_driver",
                self,
                self.source,
                self.source_fmt,
            )

    def connect_phase(self):
        if self.source_driver is not None:
            self.source_driver.seq_item_port.connect(
                self.sequencer.seq_item_export
            )

    def set_randomize(self, enable):
        self.randomize = bool(enable)
        pause_generator = _random_pause_generator() if self.randomize else None
        if self.source is not None:
            self.source.set_pause_generator(pause_generator)
        if self.sink_monitor is not None and self.sink_monitor.monitor is not None:
            self.sink_monitor.randomize = self.randomize
            if self.sink_monitor.drive_ready:
                pause_generator = (
                    _random_pause_generator() if self.randomize else None
                )
                self.sink_monitor.monitor.set_pause_generator(pause_generator)

    def cancel_bfms(self):
        for bfm in (
            self.source,
            self.source_monitor.monitor if self.source_monitor is not None else None,
            self.sink_monitor.monitor if self.sink_monitor is not None else None,
        ):
            if bfm is not None:
                bfm.cancel()

    def clear_bfms(self):
        for monitor in (self.source_monitor, self.sink_monitor):
            if monitor is not None:
                monitor.reset_protocol_state()
                if monitor.monitor is not None:
                    monitor.monitor.clear()
        if self.source is not None:
            self.source.clear()

    @property
    def source_analysis_port(self):
        if self.source_monitor is None:
            raise RuntimeError("VIP agent has no source monitor analysis port")
        return self.source_monitor.analysis_port

    @property
    def sink_analysis_port(self):
        if self.sink_monitor is None:
            raise RuntimeError("VIP agent has no sink monitor analysis port")
        return self.sink_monitor.analysis_port


class VIPSequence(uvm_sequence):
    """Sequence that sends one or more complete Intel VIP packets."""

    def __init__(self, items=None, name="vip_sequence"):
        super().__init__(name)
        self.items = list(items) if items is not None else []

    @classmethod
    def from_packets(cls, packets, name="vip_sequence"):
        return cls(
            [
                VIPItem.from_packet(packet, name=f"{name}_packet_{index}")
                for index, packet in enumerate(packets)
            ],
            name=name,
        )

    async def body(self):
        for item in self.items:
            await self.send_item(item)

    async def send_item(self, item):
        await self.start_item(item)
        await self.finish_item(item)
        return item
