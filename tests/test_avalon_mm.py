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

import logging

import pytest
from pyuvm import uvm_active_passive_enum

from cocotbext.avalon import AvalonMMBus, AvalonMMMasterBFM
from fpga_verification.sim.agents import AvalonMMAgent


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
