# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

"""Quartus hardware-in-the-loop helpers."""

from .system_console import IntelSystemConsoleSession, JtagSession

__all__ = ["IntelSystemConsoleSession", "JtagSession"]
