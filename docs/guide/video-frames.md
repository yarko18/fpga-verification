<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Video frames and payloads

The video package is independent of cocotb and protocol packets. It gives a
test one canonical numpy representation before data is packed onto a bus.
Everything on this page runs as ordinary Python.

`VideoFormat` describes sample width, plane layout and pixels transferred per
beat. `FrameSize` holds width and height separately, allowing one static
interface format to process several frame geometries.

```text
numpy frame <-> VideoPayloadCodec <-> symbols / beat payloads
```

Canonical shapes are `(height, width)` for one plane and
`(height, width, planes)` for multiple planes.

## Bus format and video format

`AvalonFormat` is a generic wire format. `VideoFormat` adds the interpretation
of samples and colour planes.

```python
from cocotbext.avalon import AvalonFormat
from fpga_verification.video import VideoFormat

avalon_fmt = AvalonFormat(
    bits_per_symbol=8,
    symbols_per_beat=4,
    first_symbol_in_high_order_bits=False,
)

fmt = VideoFormat(
    bits_per_color=10,
    number_of_color_planes=3,
    color_planes_are_in_parallel=True,
    pixels_in_parallel=2,
)

print(avalon_fmt.payload_width)
print(fmt.payload_width)
print(f"sample mask: {fmt.sample_mask:#x}")
```

With parallel planes, the samples for one pixel group share a beat. With serial
planes, samples are carried in sequence. Both are valid layouts, but the codec,
stream format and model must use the same choice.

```python
serial_fmt = VideoFormat(
    bits_per_color=10,
    number_of_color_planes=3,
    color_planes_are_in_parallel=False,
    pixels_in_parallel=2,
)

print(fmt.payload_width)
print(serial_fmt.payload_width)
```

## Geometry and generated frames

`FrameSize` states the active geometry; it is deliberately separate from the
maximum geometry in a test configuration.

```python
from fpga_verification.video import FrameSize, ImageGenerator

size = FrameSize(width=5, height=3)
print(fmt.frame_shape(size))
print(fmt.row_shape(size))
print(fmt.frame_symbol_count(size))

generator = ImageGenerator(fmt, rng=1)
black = generator.constant(size, value=0)
ramp = generator.horizontal_ramp(size)
random_frame = generator.random(size)

print(random_frame.shape)
print(random_frame.dtype)
print(random_frame[0, 0].tolist())
```

`ImageGenerator` provides deterministic constants, ramps and random frames.
Pass a seed for a failing random case so it can be reproduced. A test may plot
frames during local debug, but plotting is not part of the codec contract.

## Row packing

`VideoPayloadCodec` converts between arrays and payload symbols. `pack_row()`
pads a row to whole beats; `unpack_row()` requires that those padding symbols
are zero and removes them.

```python
from fpga_verification.video import VideoPayloadCodec

codec = VideoPayloadCodec(fmt)
row = ramp[0]

row_symbols = codec.row_to_symbols(row, size)
row_beats = codec.pack_row(row, size)
decoded_row = codec.unpack_row(row_beats, size)

print(f"pixels: {size.width}")
print(f"symbols in padded row: {len(row_symbols)}")
print(f"beats: {len(row_beats)}")
assert (decoded_row == row).all()
```

For a five-pixel row with two pixels per beat, the final beat carries one real
pixel and one zero padding pixel. This row-level padding is useful for memory
or line-oriented formats.

## Complete frames and continuous streams

`pack_frame()` uses row packing. It is the correct choice when each row starts
on a whole beat. `frame_to_symbols()` instead returns one continuous raster
stream without row padding; a later protocol layer handles the incomplete last
beat.

```python
from fpga_verification.video import compare_frames

packed = codec.pack_frame(random_frame, size)
decoded = codec.unpack_frame(packed, size)
compare_frames(decoded, random_frame)

symbols = codec.frame_to_symbols(random_frame, size)
decoded_symbols = codec.symbols_to_frame(symbols, size)
compare_frames(decoded_symbols, random_frame)
```

Use `validate_frame()` before a custom conversion to check shape, dtype and
sample range. `frame_to_rows()` and `rows_to_frame()` help when an interface or
model processes one row at a time.

```python
validated = codec.validate_frame(random_frame, size)
rows = codec.frame_to_rows(validated, size)
round_trip = codec.rows_to_frame(rows, size)
compare_frames(round_trip, random_frame)
```

## Comparing expected and observed frames

`compare_frames()` raises an informative assertion that identifies a mismatch.
A tolerance is appropriate only when the hardware contract permits a bounded
numeric error.

```python
observed = random_frame.copy()
observed[0, 0, 0] += 1

compare_frames(observed, random_frame, tolerance=1)

try:
    compare_frames(observed, random_frame)
except AssertionError as error:
    print(error)
```

Do not use a tolerance to hide packet-order, geometry, or format errors. Those
belong in the protocol checker and scoreboard.
