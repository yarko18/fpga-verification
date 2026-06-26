# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pytest

from fpga_verification.video import (
    FrameSize,
    ImageGenerator,
    VideoFormat,
    VideoPayloadCodec,
    compare_frames,
)


@pytest.mark.parametrize(
    "fmt,size",
    [
        (VideoFormat(8), FrameSize(5, 3)),
        (VideoFormat(10, pixels_in_parallel=2), FrameSize(5, 3)),
        (VideoFormat(12, 3, True, 2), FrameSize(5, 3)),
        (VideoFormat(12, 3, False, 2), FrameSize(5, 3)),
        (VideoFormat(16, 4, True, 4), FrameSize(3, 2)),
        (VideoFormat(16, 4, False, 4), FrameSize(3, 2)),
    ],
)
def test_payload_round_trip(fmt, size):
    generator = ImageGenerator(fmt, rng=123)
    frame = generator.random(size)
    codec = VideoPayloadCodec(fmt)

    assert np.array_equal(
        codec.unpack_frame(codec.pack_frame(frame, size), size),
        frame,
    )
    assert np.array_equal(
        codec.symbols_to_frame(codec.frame_to_symbols(frame, size), size),
        frame,
    )
    assert np.array_equal(
        codec.rows_to_frame(codec.frame_to_rows(frame, size), size),
        frame,
    )


def test_video_format_does_not_contain_frame_geometry():
    fmt = VideoFormat(8, 3, True, 2)
    assert not hasattr(fmt, "width")
    assert not hasattr(fmt, "height")
    assert fmt.frame_shape(FrameSize(5, 3)) == (3, 5, 3)
    assert fmt.frame_shape(FrameSize(7, 2)) == (2, 7, 3)


def test_parallel_plane_wire_order_and_little_endian_packing():
    fmt = VideoFormat(8, 3, True, 2)
    size = FrameSize(3, 1)
    row = np.arange(1, 10, dtype=np.uint8).reshape(3, 3)
    codec = VideoPayloadCodec(fmt)

    assert codec.row_to_symbols(row, size) == [
        1, 2, 3, 4, 5, 6,
        7, 8, 9, 0, 0, 0,
    ]
    assert codec.pack_row(row, size)[0] == 0x060504030201
    assert np.array_equal(
        codec.unpack_row(codec.pack_row(row, size), size),
        row,
    )


def test_serial_plane_wire_order():
    fmt = VideoFormat(8, 3, False, 2)
    size = FrameSize(3, 1)
    row = np.arange(1, 10, dtype=np.uint8).reshape(3, 3)
    codec = VideoPayloadCodec(fmt)

    assert codec.row_to_symbols(row, size) == [
        1, 4, 2, 5, 3, 6,
        7, 0, 8, 0, 9, 0,
    ]
    assert codec.pack_row(row, size) == [
        0x0401,
        0x0502,
        0x0603,
        0x0007,
        0x0008,
        0x0009,
    ]
    assert np.array_equal(
        codec.unpack_row(codec.pack_row(row, size), size),
        row,
    )


def test_frame_symbols_are_continuous_without_row_padding():
    fmt = VideoFormat(8, pixels_in_parallel=4)
    size = FrameSize(3, 2)
    frame = np.arange(1, 7, dtype=np.uint8).reshape(2, 3)
    codec = VideoPayloadCodec(fmt)

    assert codec.row_to_symbols(frame[0], size) == [1, 2, 3, 0]
    assert codec.row_to_symbols(frame[1], size) == [4, 5, 6, 0]
    assert codec.frame_to_symbols(frame, size) == [1, 2, 3, 4, 5, 6]
    assert fmt.frame_symbol_count(size) == 6
    assert fmt.frame_beat_count(size) == 2
    assert fmt.frame_padding_symbols(size) == 2
    assert np.array_equal(
        codec.symbols_to_frame([1, 2, 3, 4, 5, 6], size),
        frame,
    )


def test_serial_frame_symbols_cross_row_boundaries_without_padding():
    fmt = VideoFormat(8, 3, False, 4)
    size = FrameSize(3, 2)
    frame = np.arange(1, 19, dtype=np.uint8).reshape(2, 3, 3)
    codec = VideoPayloadCodec(fmt)

    assert codec.frame_to_symbols(frame, size) == [
        1, 4, 7, 10,
        2, 5, 8, 11,
        3, 6, 9, 12,
        13, 16,
        14, 17,
        15, 18,
    ]
    assert np.array_equal(
        codec.symbols_to_frame(codec.frame_to_symbols(frame, size), size),
        frame,
    )


def test_non_zero_padding_is_rejected():
    fmt = VideoFormat(8, pixels_in_parallel=2)
    size = FrameSize(3, 1)
    codec = VideoPayloadCodec(fmt)

    with pytest.raises(ValueError, match="non-zero padding"):
        codec.symbols_to_row([1, 2, 3, 1], size)


def test_frame_validation_is_strict():
    fmt = VideoFormat(8)
    size = FrameSize(2, 2)
    codec = VideoPayloadCodec(fmt)

    with pytest.raises(ValueError, match="shape"):
        codec.validate_frame(np.zeros((2, 3), dtype=np.uint8), size)
    with pytest.raises(ValueError, match="does not fit"):
        codec.validate_frame(np.full((2, 2), 256, dtype=np.uint16), size)
    with pytest.raises(ValueError, match="does not fit"):
        codec.validate_frame(np.full((2, 2), -1, dtype=np.int16), size)
    with pytest.raises(TypeError, match="integers"):
        codec.validate_frame(np.zeros((2, 2), dtype=np.float32), size)
    with pytest.raises(TypeError, match="FrameSize"):
        codec.validate_frame(np.zeros((2, 2), dtype=np.uint8), (2, 2))


def test_generators_are_seeded_and_use_inclusive_bounds():
    fmt = VideoFormat(8)
    size = FrameSize(8, 4)
    left = ImageGenerator(fmt, rng=42).random(size, 7, 7)
    right = ImageGenerator(fmt, rng=42).random(size, 7, 7)

    assert np.array_equal(left, right)
    assert np.all(left == 7)
    assert ImageGenerator(fmt).constant(size, 3).dtype == np.uint8

    with pytest.raises(ValueError):
        ImageGenerator(fmt).constant(size, -1)
    with pytest.raises(ValueError):
        ImageGenerator(fmt).linspace(size, 0, 256)


def test_horizontal_ramp_repeats_rows_and_planes():
    fmt = VideoFormat(8, 3)
    size = FrameSize(4, 2)
    frame = ImageGenerator(fmt).horizontal_ramp(size, 1, 4)

    assert frame.shape == (2, 4, 3)
    assert np.array_equal(frame[0, :, 0], np.arange(1, 5))
    assert np.array_equal(frame[0], frame[1])
    assert np.array_equal(frame[:, :, 0], frame[:, :, 2])


def test_one_codec_handles_multiple_frame_sizes():
    fmt = VideoFormat(10, pixels_in_parallel=2)
    generator = ImageGenerator(fmt, rng=9)
    codec = VideoPayloadCodec(fmt)

    for size in (FrameSize(4, 3), FrameSize(7, 2), FrameSize(5, 5)):
        frame = generator.random(size)
        payload = codec.pack_frame(frame, size)
        assert np.array_equal(codec.unpack_frame(payload, size), frame)


def test_compare_frames_reports_first_coordinate():
    actual = np.zeros((2, 2, 2), dtype=np.uint8)
    expected = actual.copy()
    expected[1, 0, 1] = 3

    assert compare_frames(actual, actual)
    assert compare_frames(actual, expected, tolerance=3)
    with pytest.raises(AssertionError, match="y=1, x=0, plane=1"):
        compare_frames(actual, expected, tolerance=2)
