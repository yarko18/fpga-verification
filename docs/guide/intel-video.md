<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Intel Avalon-ST Video

The Intel video layer gives meaning to an Avalon-ST symbol stream while
remaining independent of the simulator.

```text
numpy frame <-> IntelVIPFrameCodec <-> VIP packet objects
                                         |
                                  to_symbols / decoder
                                         |
                                  Avalon-ST frames
```

The packet model represents control, user, and video packets explicitly:

- `VIPControlPacket` carries width, height, and interlacing;
- `VIPUserPacket` carries a user type and payload;
- `VIPVideoPacket` carries raster-order video samples;
- `VIPFrame` groups the packets belonging to one logical frame.

```python
from fpga_verification.protocols.avalon_st.intel_video import (
    VIPControlPacket,
    VIPInterlacing,
    vip_packet_from_symbols,
)

control = VIPControlPacket(
    width=1920,
    height=1080,
    interlacing=VIPInterlacing.PROGRESSIVE_FRAME,
)
decoded = vip_packet_from_symbols(control.to_symbols())
```

`IntelVIPFrameCodec` combines the neutral video codec with packet creation and
decoding. `VIPProtocolChecker` owns stream history such as the active control
resolution and checks control-before-video ordering. Keeping that state out of
the packet codec lets the same codec be reused for isolated unit tests.

In simulation, `VIPDriver` serializes packet objects and `VIPMonitor`
reconstructs them. `VIPAgent` assembles the source and sink sides for a pyuvm
environment.

The
[Intel video notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/05_intel_vip_packets_and_agent.ipynb)
contains packet, codec, checker, and agent examples.

Next: [build a complete VIP verification path](vip-verification.md).
