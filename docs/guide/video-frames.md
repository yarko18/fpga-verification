<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Video frames

The video package is independent of cocotb and protocol packet types. It gives
tests one canonical numpy representation before data is placed on a bus.

`VideoFormat` describes color sample width, plane layout, and pixels per beat.
`FrameSize` holds width and height separately, allowing one static interface
format to process changing resolutions.

Canonical shapes are `(height, width)` for one plane and
`(height, width, planes)` for multiple planes.

```python
fmt = VideoFormat(
    bits_per_color=10,
    number_of_color_planes=3,
    color_planes_are_in_parallel=True,
    pixels_in_parallel=2,
)
size = FrameSize(width=640, height=480)
frame = ImageGenerator(fmt, rng=1).random(size)

codec = VideoPayloadCodec(fmt)
payload = codec.pack_frame(frame, size)
decoded = codec.unpack_frame(payload, size)
compare_frames(decoded, frame)
```

`ImageGenerator` creates deterministic constant, ramp, linspace, and random
stimulus. `VideoPayloadCodec` converts frames, rows, symbols, and packed beats
while validating shape, range, payload length, and padding. `compare_frames()`
reports the first mismatch and supports an explicit tolerance.

The
[video frames notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/02_video_frames.ipynb)
explains parallel and serial plane layouts in detail.

Next: [numeric storage formats](numeric-formats.md).
