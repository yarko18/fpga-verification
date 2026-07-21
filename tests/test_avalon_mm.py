# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import logging

import pytest
from pyuvm import uvm_active_passive_enum

from fpga_verification.sim.agents import AvalonMMAgent
from fpga_verification.sim.buses import AvalonMMBus, AvalonMMMasterBFM


class _Signal:
    def __init__(self, width):
        self.width = width
        self.value = 0

    def __len__(self):
        return self.width


def _bus():
    return AvalonMMBus(
        address=_Signal(8),
        writedata=_Signal(32),
        write=_Signal(1),
        read=_Signal(1),
        readdata=_Signal(32),
        byteenable=_Signal(4),
        label="test_mm",
    )


def test_master_packet_log_level_accepts_string():
    bfm = AvalonMMMasterBFM(
        _bus(),
        clock=object(),
        packet_logging=True,
        packet_log_level="debug",
    )

    assert bfm.packet_logging is True
    assert bfm.packet_log_level == logging.DEBUG


def test_master_set_packet_logging_updates_level():
    bfm = AvalonMMMasterBFM(_bus(), clock=object())

    bfm.set_packet_logging(True, "warning")

    assert bfm.packet_logging is True
    assert bfm.packet_log_level == logging.WARNING


def test_master_packet_log_level_rejects_unknown_string():
    with pytest.raises(ValueError, match="Unknown log level"):
        AvalonMMMasterBFM(_bus(), clock=object(), packet_log_level="verbose")


def test_passive_agent_routes_packet_logging_to_monitor():
    agent = AvalonMMAgent(
        "passive_agent",
        None,
        _bus(),
        clock=object(),
        packet_logging=True,
        packet_log_level="warning",
    )

    agent.build_phase()

    assert agent.monitor.packet_logging is True
    assert agent.monitor.packet_log_level == logging.WARNING
    assert agent.master is None


def test_active_agent_routes_packet_logging_to_master():
    agent = AvalonMMAgent(
        "active_agent",
        None,
        _bus(),
        clock=object(),
        is_active=uvm_active_passive_enum.UVM_ACTIVE,
        packet_logging=True,
        packet_log_level="warning",
    )

    agent.build_phase()

    assert agent.monitor.packet_logging is False
    assert agent.master.packet_logging is True
    assert agent.master.packet_log_level == logging.WARNING
