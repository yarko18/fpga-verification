# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import logging

from cocotb.triggers import RisingEdge
from pyuvm import (
    uvm_active_passive_enum,
    uvm_agent,
    uvm_analysis_port,
    uvm_monitor,
)

from fpga_verification.sim.buses.avalon_mm import (
    AvalonMMMasterBFM,
    AvalonMMTransaction,
)


def _signal_width(signal):
    try:
        return len(signal)
    except TypeError:
        return 1


def _mask(width):
    return (1 << int(width)) - 1


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


def _bus_label(bus):
    return getattr(bus, "label", None) or "avalon_mm"


def _normalize_log_level(level):
    if isinstance(level, str):
        normalized = logging.getLevelName(level.upper())
        if isinstance(normalized, int):
            return normalized
        raise ValueError(f"Unknown log level: {level}")
    return int(level)


def _byteenable_width(bus):
    if bus.byteenable is not None:
        return _signal_width(bus.byteenable)
    if bus.writedata is not None:
        return _signal_width(bus.writedata) // 8
    if bus.readdata is not None:
        return _signal_width(bus.readdata) // 8
    return 0


class AvalonMMMonitor(uvm_monitor):
    """Passively observes accepted Avalon-MM read/write requests."""

    def __init__(
        self,
        name,
        parent,
        bus,
        clock,
        reset=None,
        reset_active_level=True,
        packet_logging=False,
        packet_log_level=logging.INFO,
    ):
        super().__init__(name, parent)
        self.bus = bus
        self.clock = clock
        self.reset = reset
        self.reset_active_level = bool(reset_active_level)
        self.packet_logging = bool(packet_logging)
        self.packet_log_level = _normalize_log_level(packet_log_level)
        self.label = _bus_label(bus)
        self.log = logging.getLogger(f"cocotb.{self.label}.monitor")
        self.analysis_port = uvm_analysis_port("analysis_port", self)

    async def run_phase(self):
        while True:
            await RisingEdge(self.clock)

            if self._reset_active():
                continue

            if self._waitrequest_active():
                continue

            read = bool(_read_int(self.bus.read, "read", 0))
            write = bool(_read_int(self.bus.write, "write", 0))

            if read and write:
                raise RuntimeError(
                    f"{self.label}: Avalon-MM read and write asserted together"
                )
            if not read and not write:
                continue

            transaction = self._sample_transaction("write" if write else "read")
            self.analysis_port.write(transaction)

            if self.packet_logging:
                self._log_transaction(transaction)

    def _sample_transaction(self, kind):
        address = _read_int(self.bus.address, "address")
        byteenable = _read_int(
            self.bus.byteenable,
            "byteenable",
            _mask(_byteenable_width(self.bus)),
        )
        burstcount = _read_int(self.bus.burstcount, "burstcount", 1)
        data = (
            _read_int(self.bus.writedata, "writedata")
            if kind == "write"
            else None
        )

        return AvalonMMTransaction(
            kind=kind,
            address=address,
            data=data,
            byteenable=byteenable,
            burstcount=burstcount,
            beat_index=0,
        )

    def _waitrequest_active(self):
        return bool(_read_int(self.bus.waitrequest, "waitrequest", 0))

    def _reset_active(self):
        if self.reset is None:
            return False
        return _read_int(
            self.reset,
            "reset",
            int(self.reset_active_level),
        ) == int(self.reset_active_level)

    def _log_transaction(self, transaction):
        data = ""
        if transaction.data is not None:
            data = f" data=0x{transaction.data:X}"

        self.log.log(
            self.packet_log_level,
            "%s: observed avalon-mm %s address=0x%X%s byteenable=0x%X",
            self.label,
            transaction.kind,
            transaction.address,
            data,
            transaction.byteenable,
        )


class AvalonMMAgent(uvm_agent):
    """Avalon-MM pyuvm agent with an always-on monitor and optional master."""

    def __init__(
        self,
        name,
        parent,
        bus,
        clock,
        reset=None,
        reset_active_level=True,
        is_active=uvm_active_passive_enum.UVM_PASSIVE,
        packet_logging=False,
        packet_log_level=logging.INFO,
        read_response_latency=0,
        default_byteenable=None,
        master_packet_logging=False,
        master_packet_log_level=logging.INFO,
    ):
        super().__init__(name, parent)
        self.bus = bus
        self.clock = clock
        self.reset = reset
        self.reset_active_level = bool(reset_active_level)
        self._requested_is_active = is_active
        self.packet_logging = bool(packet_logging)
        self.packet_log_level = _normalize_log_level(packet_log_level)
        self.read_response_latency = int(read_response_latency)
        self.default_byteenable = default_byteenable
        self._master_packet_logging = bool(master_packet_logging)
        self._master_packet_log_level = _normalize_log_level(master_packet_log_level)

        self.monitor = None
        self.master = None

    def build_phase(self):
        super().build_phase()
        self.is_active = self._requested_is_active

        self.monitor = AvalonMMMonitor(
            "monitor",
            self,
            bus=self.bus,
            clock=self.clock,
            reset=self.reset,
            reset_active_level=self.reset_active_level,
            packet_logging=self.packet_logging,
            packet_log_level=self.packet_log_level,
        )

        if self.active():
            self.master = AvalonMMMasterBFM(
                self.bus,
                self.clock,
                self.reset,
                read_response_latency=self.read_response_latency,
                default_byteenable=self.default_byteenable,
                packet_logging=self._master_packet_logging,
                packet_log_level=self._master_packet_log_level,
            )

    async def run_phase(self):
        if self.master is not None:
            self.master.start()

    @property
    def analysis_port(self):
        if self.monitor is None:
            raise RuntimeError("Avalon-MM agent has no monitor analysis port")
        return self.monitor.analysis_port
