<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Intel Avalon-ST Video

The Intel video layer gives packet meaning to an Avalon-ST symbol stream while
remaining independent of a simulator. It represents control, user and video
packets explicitly, converts numpy frames to packet symbols, and validates
packet-stream order.

```text
numpy frame <-> IntelVIPFrameCodec <-> VIP packet objects <-> Avalon-ST frames
```

## Packet model

The packet classes are ordinary Python objects. A `VIPFrame` groups the packets
belonging to one logical frame; individual packet objects remain visible so a
test can check ordering and sideband traffic.

```python
from fpga_verification.protocols.avalon_st.intel_video import (
    VIPControlPacket,
    VIPFrame,
    VIPInterlacing,
    VIPPacketType,
    VIPUserPacket,
    VIPVideoPacket,
    vip_packet_from_symbols,
)

control = VIPControlPacket(
    width=640,
    height=480,
    interlacing=VIPInterlacing.PROGRESSIVE_FRAME,
)

symbols = control.to_symbols()
assert vip_packet_from_symbols(symbols) == control

for packet_type in VIPPacketType:
    print(packet_type.name, hex(int(packet_type)))
```

A control packet carries geometry and interlacing state. A user packet carries
a user type and payload. A video packet carries raster-order payload symbols.
Control payload is padded to a whole beat; the final beat of a user or video
packet is described by Avalon-ST `empty`.

```python
user = VIPUserPacket(user_type=1, payload=[0xA, 0xB])
video = VIPVideoPacket(payload=[10, 20, 30, 40])

for packet in (user, control, video):
    wire = packet.to_symbols(symbols_per_beat=3)
    assert vip_packet_from_symbols(wire, symbols_per_beat=3) == packet
```

## `VIPFrame`

`VIPFrame` is a convenient packet group for one logical frame. It can emit the
control packet, video packet and its complete ordered packet sequence.

```python
vip_frame = VIPFrame(
    width=2,
    height=2,
    pixels=[0x10, 0x20, 0x30, 0x40],
    user_packets=[VIPUserPacket(2, [0x55])],
)

print(vip_frame.control_packet())
print(vip_frame.video_packet())
print([packet.packet_type.name for packet in vip_frame.packets()])
```

Use individual packets at a driver and monitor boundary; use `VIPFrame` where
the test is naturally about a complete frame.

## Frame codec

`IntelVIPFrameCodec` combines the neutral video representation with packet
creation and decoding. Its smaller helpers include `control_packet()`,
`frame_to_video_packet()`, `video_packet_to_frame()`, `frame_to_vip()` and
`vip_to_frame()`.

```python
from fpga_verification.protocols.avalon_st.intel_video import IntelVIPFrameCodec
from fpga_verification.video import (
    FrameSize,
    ImageGenerator,
    VideoFormat,
    compare_frames,
)

fmt = VideoFormat(
    bits_per_color=8,
    number_of_color_planes=3,
    pixels_in_parallel=2,
)
size = FrameSize(width=5, height=3)
image = ImageGenerator(fmt, rng=1).horizontal_ramp(size)
codec = IntelVIPFrameCodec(fmt)

packets = codec.frame_to_packets(image, size)
packet_symbols = codec.frame_to_packet_symbols(image, size)
decoded = codec.packet_symbols_to_frame(packet_symbols, size)

compare_frames(decoded, image)
print([type(packet).__name__ for packet in packets])
```

The codec does not keep stream history. That makes an isolated packet or frame
round trip easy to unit-test.

## Protocol checker

`VIPProtocolChecker` owns the history that does not belong in a stateless
codec: active control geometry and control-before-video order. It should be
used by a monitor or scoreboard that sees the complete packet stream.

```python
from fpga_verification.protocols.avalon_st.intel_video import (
    VIPProtocolChecker,
    VIPProtocolError,
)

checker = VIPProtocolChecker(fmt)
checker.check_video_packet_size = True

for packet in packets:
    checker.observe(packet)

print(checker.control_size)
print(checker.expected_video_symbols())

checker.reset()
try:
    checker.observe(VIPVideoPacket([0]))
except VIPProtocolError as error:
    print(type(error).__name__, error)
```

The checker deliberately validates protocol history, not DUT behavior. The
custom scoreboard converts decoded packets to domain values and asks the
behavior model for expected output.

Next: [build that verification environment](vip-verification.md).
