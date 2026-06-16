<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: Apache-2.0
-->

# Intel Avalon-ST Video Protocol

Reference documentation: [Video and Image Processing Suite](https://docs.altera.com/r/docs/683416/22.1/video-and-image-processing-suite-user-guide/about-the-video-and-image-processing-suite)

```python
from fpga_verification.protocols.avalon_st.intel_video import VIPControlPacket
```


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
