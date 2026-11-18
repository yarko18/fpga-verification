# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Reusable functional coverage for Avalon-ST Video VIP transactions."""

from __future__ import annotations

from collections.abc import Sequence

from fpga_verification.sim.coverage import CoverageGroup, CoverageScope

from .packets import VIPPacket, VIPPacketType


VIP_PACKET_KINDS = ("video", "control", "user", "ancillary")


def vip_packet_kind(packet: VIPPacket) -> str:
    """Classify a VIP packet without exposing individual user type values."""
    if not isinstance(packet, VIPPacket):
        raise TypeError("VIP packet coverage expects a VIPPacket")
    if packet.packet_type is VIPPacketType.VIDEO:
        return "video"
    if packet.packet_type is VIPPacketType.CONTROL:
        return "control"
    if packet.packet_type is VIPPacketType.ANCILLARY:
        return "ancillary"
    return "user"


class VIPPacketCoverage(CoverageGroup):
    """Protocol-level packet-kind coverage for one stream endpoint."""

    def __init__(
        self,
        scope: CoverageScope,
        *,
        expected_kinds: Sequence[str] = VIP_PACKET_KINDS,
    ):
        from cocotb_coverage.coverage import CoverPoint

        kinds = tuple(expected_kinds)
        unknown = set(kinds) - set(VIP_PACKET_KINDS)
        if unknown:
            raise ValueError(
                "unknown VIP packet coverage kinds: "
                + ", ".join(sorted(unknown))
            )
        super().__init__(
            CoverPoint(
                scope.item("packet_kind"),
                xf=vip_packet_kind,
                bins=list(kinds),
            )
        )
