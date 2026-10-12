# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Quartus hardware-in-the-loop helpers."""

from .system_console import IntelSystemConsoleSession, JtagSession

__all__ = ["IntelSystemConsoleSession", "JtagSession"]
