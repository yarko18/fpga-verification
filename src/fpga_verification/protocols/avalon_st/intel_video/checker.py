# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""Stateful protocol checks for an Intel Avalon-ST Video packet stream."""
import logging
from fpga_verification.video import FrameSize, VideoFormat
from .packets import VIPControlPacket, VIPPacket, VIPVideoPacket


class VIPProtocolError(ValueError):
    """Intel VIP packet ordering or declared-frame-size violation."""


class VIPProtocolChecker:
    """Validate control/video ordering without converting packets to frames.

    The checker is intentionally separate from the stateless frame codec. One
    checker instance represents one observed packet stream.
    """

    def __init__(self, fmt):
        if not isinstance(fmt, VideoFormat):
            raise TypeError("fmt must be a VideoFormat")
        self.fmt = fmt
        self._control_size = None
        self.check_video_packet_size = False
        self.log = logging.getLogger("cocotb.fpga_verification.vip_protocol_checker")

    @property
    def control_size(self):
        return self._control_size

    def reset(self):
        self._control_size = None

    def expected_video_symbols(self, size=None):
        size = self._control_size if size is None else size
        if not isinstance(size, FrameSize):
            raise TypeError("size must be a FrameSize")
        return self.fmt.frame_symbol_count(size)

    def observe(self, packet):
        if not isinstance(packet, VIPPacket):
            raise TypeError("packet must be a VIPPacket")

        if isinstance(packet, VIPControlPacket):
            try:
                self._control_size = FrameSize(packet.width, packet.height)
            except (TypeError, ValueError) as exc:
                raise VIPProtocolError(
                    "VIP control packet must declare a positive frame size"
                ) from exc
            return packet

        if isinstance(packet, VIPVideoPacket):
            if self._control_size is None:
                raise VIPProtocolError(
                    "VIP video packet received before any control packet"
                )

            actual = len(packet.payload)
            expected = self.expected_video_symbols()
            if actual != expected:
                size = self._control_size
                msg = "VIP video payload does not match the active control " \
                        f"resolution {size.width}x{size.height}: " \
                        f"got {actual} symbols, expected {expected}. " \
                        "A new control packet is required before a frame-size " \
                        "change."
                if self.check_video_packet_size:
                    raise VIPProtocolError(msg)
                else:
                    self.log.warning(msg)
        return packet
