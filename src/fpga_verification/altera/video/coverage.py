# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Reusable functional coverage for Avalon-ST Video VIP transactions."""

from __future__ import annotations

from collections.abc import Sequence

from fpga_verification.sim.coverage import CoverageGroup, CoverageScope

from .packets import VIPPacket, VIPPacketType


VIP_PACKET_KINDS = ("video", "control", "user", "ancillary")
"""Broad protocol packet categories."""

VIP_PACKET_TYPES = (
    "video",
    "control",
    "ancillary",
    *(f"user{user_type}" for user_type in range(1, 9)),
)
"""Individual packet types encoded by :class:`VIPPacketType`."""


def vip_packet_kind(packet: VIPPacket) -> str:
    """Classify a VIP packet by its broad protocol category."""
    if not isinstance(packet, VIPPacket):
        raise TypeError("VIP packet coverage expects a VIPPacket")
    packet_type = _packet_type(packet)
    return (
        "user"
        if packet_type.name.startswith("USER")
        else packet_type.name.lower()
    )


def vip_packet_type(packet: VIPPacket) -> str:
    """Return a packet's exact VIP type, including ``user1`` through ``user8``."""
    if not isinstance(packet, VIPPacket):
        raise TypeError("VIP packet coverage expects a VIPPacket")
    return _packet_type(packet).name.lower()


def _packet_type(packet: VIPPacket) -> VIPPacketType:
    try:
        return VIPPacketType(packet.packet_type)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"unsupported VIP packet type: {packet.packet_type!r}"
        ) from error


class VIPPacketCoverage(CoverageGroup):
    """Broad category and exact packet-type coverage for one stream endpoint."""

    def __init__(
        self,
        scope: CoverageScope,
        *,
        expected_kinds: Sequence[str] = VIP_PACKET_KINDS,
        expected_types: Sequence[str] | None = None,
    ):
        from cocotb_coverage.coverage import CoverPoint

        kinds = tuple(expected_kinds)
        if not kinds:
            raise ValueError("expected_kinds must not be empty")
        if len(set(kinds)) != len(kinds):
            raise ValueError("expected_kinds must not contain duplicates")
        unknown = set(kinds) - set(VIP_PACKET_KINDS)
        if unknown:
            raise ValueError(
                "unknown VIP packet coverage kinds: "
                + ", ".join(sorted(unknown))
            )
        types = (
            tuple(
                packet_type
                for packet_type in VIP_PACKET_TYPES
                if packet_type in kinds
                or (packet_type.startswith("user") and "user" in kinds)
            )
            if expected_types is None
            else tuple(expected_types)
        )
        if not types:
            raise ValueError("expected_types must not be empty")
        if len(set(types)) != len(types):
            raise ValueError("expected_types must not contain duplicates")
        unknown = set(types) - set(VIP_PACKET_TYPES)
        if unknown:
            raise ValueError(
                "unknown VIP packet coverage types: "
                + ", ".join(sorted(unknown))
            )
        super().__init__(
            CoverPoint(
                scope.item("packet_kind"),
                xf=vip_packet_kind,
                bins=list(kinds),
            ),
            CoverPoint(
                scope.item("packet_type"),
                xf=vip_packet_type,
                bins=list(types),
            ),
        )
