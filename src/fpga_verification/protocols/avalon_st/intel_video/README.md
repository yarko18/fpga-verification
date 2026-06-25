<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: Apache-2.0
-->

# Intel Avalon-ST Video Protocol

Reference documentation: [Video and Image Processing Suite](https://docs.altera.com/r/docs/683416/22.1/video-and-image-processing-suite-user-guide/about-the-video-and-image-processing-suite)

```python
from fpga_verification.protocols.avalon_st.intel_video import (
    IntelVIPFrameCodec,
    VIPControlPacket,
)
from fpga_verification.video import FrameSize, ImageGenerator, VideoFormat

fmt = VideoFormat(
    bits_per_symbol=10,
    pixels_in_parallel=2,
)
size = FrameSize(width=640, height=480)
frame = ImageGenerator(fmt, rng=1).random(size)
codec = IntelVIPFrameCodec(fmt)

packet_symbols = codec.frame_to_packet_symbols(frame, size)
decoded = codec.packet_symbols_to_frame(packet_symbols, size)
```

Every encoded packet starts with a complete identifier beat. Unused symbols
in that beat and final partial beats are zero padded.

Pixel decoding always uses the explicit `FrameSize`; it never derives geometry
from the control packet. Control validation is a separate operation:

```python
codec.validate_control_packet(control_packet, size)
```

The codec is stateless. User, control, and video packet adapters do not retain
packet history and do not run an internal state machine.


### Packet Type Identifiers

| Type Identifier D0[3:0] | Description                              |
| ----------------------- | ---------------------------------------- |
| 0x0 (0)                 | Video data packet                        |
| 0x1–0x8 (1–8)           | User data packet                         |
| 0x9–0xC (9–12)          | Reserved                                 |
| 0xD (13)                | Clocked Video data ancillary user packet |
| 0xE (14)                | Reserved                                 |
| 0xF (15)                | Control packet                           |


### Interlaced Nibble of Control Packet

| Interlaced/Progressive | Interlacing[3:0] | Description                                                          |
| ---------------------- | ---------------- | -------------------------------------------------------------------- |
| Interlaced             | 0b1100             | Interlaced F1 field, paired with the following F0 field              |
| Interlaced             | 0b1101             | Interlaced F1 field, paired with the preceding F0 field              |
| Interlaced             | 0b111x             | Interlaced F1 field, pairing don’t care                              |
| Interlaced             | 0b1000             | Interlaced F0 field, paired with the preceding F1 field              |
| Interlaced             | 0b1001             | Interlaced F0 field, paired with the following F1 field              |
| Interlaced             | 0b101x             | Interlaced F0 field,pairing don’t care                               |
| Progressive            | 0b0x01             | Progressive 0 x 0 1 Progressive frame, deinterlaced from an f1 field |
| Progressive            | 0b0x00             | Progressive frame, deinterlaced from an f0 field                     |
| Progressive            | 0b0x1x             | Progressive frame                                                    |

## Python structure:

`VIPPacket`:
 - `VIPControlPacket`
 - `VIPVideoPacket`
 - `VIPUserPacket`

`VIPFrame`
 - control packet
 - optional user packets
 - video packet
