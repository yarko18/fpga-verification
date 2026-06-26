# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""Neutral numpy frame model and Avalon-ST video payload packing."""

from dataclasses import dataclass
from numbers import Integral

import numpy as np

from fpga_verification.formats import UIntFormat
from fpga_verification.sim.buses.avalon_st import AvalonFormat


@dataclass(frozen=True)
class FrameSize:
    """Geometry of one video frame."""

    width: int
    height: int

    def __post_init__(self):
        for name in ("width", "height"):
            value = getattr(self, name)
            if not isinstance(value, Integral):
                raise TypeError(f"{name} must be an integer")
            if int(value) <= 0:
                raise ValueError(f"{name} must be > 0, got {value}")


@dataclass(frozen=True)
class VideoFormat(AvalonFormat):
    """Static sample layout of a video stream interface."""

    bits_per_color: int
    number_of_color_planes: int = 1
    color_planes_are_in_parallel: bool = True
    pixels_in_parallel: int = 1

    def __post_init__(self):
        for name in (
            "bits_per_color",
            "number_of_color_planes",
            "pixels_in_parallel",
        ):
            value = getattr(self, name)
            if not isinstance(value, Integral):
                raise TypeError(f"{name} must be an integer")
            if int(value) <= 0:
                raise ValueError(f"{name} must be > 0, got {value}")

        UIntFormat(int(self.bits_per_color))
        object.__setattr__(
            self,
            "color_planes_are_in_parallel",
            bool(self.color_planes_are_in_parallel),
        )

    @property
    def bits_per_symbol(self):
        return int(self.bits_per_color)

    @property
    def symbols_per_beat(self):
        return self.samples_per_beat

    @property
    def first_symbol_in_high_order_bits(self):
        return False

    @property
    def sample_format(self):
        return UIntFormat(int(self.bits_per_color))

    @property
    def dtype(self):
        return self.sample_format.dtype

    @property
    def sample_mask(self):
        return self.sample_format.mask

    @property
    def samples_per_beat(self):
        planes = (
            int(self.number_of_color_planes)
            if self.color_planes_are_in_parallel
            else 1
        )
        return int(self.pixels_in_parallel) * planes

    @property
    def payload_width(self):
        return int(self.bits_per_color) * self.samples_per_beat

    def frame_shape(self, size):
        size = _require_frame_size(size)
        if self.number_of_color_planes == 1:
            return (int(size.height), int(size.width))
        return (
            int(size.height),
            int(size.width),
            int(self.number_of_color_planes),
        )

    def row_shape(self, size):
        size = _require_frame_size(size)
        if self.number_of_color_planes == 1:
            return (int(size.width),)
        return (int(size.width), int(self.number_of_color_planes))

    def beats_per_row(self, size):
        size = _require_frame_size(size)
        pixel_groups = (
            int(size.width) + int(self.pixels_in_parallel) - 1
        ) // int(self.pixels_in_parallel)
        if self.color_planes_are_in_parallel:
            return pixel_groups
        return pixel_groups * int(self.number_of_color_planes)

    def symbols_per_row(self, size):
        return self.beats_per_row(size) * self.samples_per_beat

    def frame_symbol_count(self, size):
        size = _require_frame_size(size)
        return (
            int(size.width)
            * int(size.height)
            * int(self.number_of_color_planes)
        )

    def frame_beat_count(self, size):
        symbols = self.frame_symbol_count(size)
        return (symbols + self.samples_per_beat - 1) // self.samples_per_beat

    def frame_padding_symbols(self, size):
        return (
            self.frame_beat_count(size) * self.samples_per_beat
            - self.frame_symbol_count(size)
        )


class ImageGenerator:
    """Generate numpy frames for an explicit format and frame size."""

    def __init__(self, fmt, rng=None):
        if not isinstance(fmt, VideoFormat):
            raise TypeError("fmt must be a VideoFormat")
        self.fmt = fmt
        self.rng = (
            rng
            if isinstance(rng, np.random.Generator)
            else np.random.default_rng(rng)
        )

    def constant(self, size, value=0, dtype=None):
        size = _require_frame_size(size)
        dtype = self._dtype(dtype)
        self._validate_range(value, value)
        frame = np.full(self.fmt.frame_shape(size), value, dtype=dtype)
        return self._validate_generated(frame, size)

    def linspace(self, size, start=0, stop=None, dtype=None):
        size = _require_frame_size(size)
        dtype = self._dtype(dtype)
        stop = self._default_max(dtype) if stop is None else stop
        self._validate_range(start, stop)
        frame = np.linspace(
            start,
            stop,
            num=int(np.prod(self.fmt.frame_shape(size))),
            dtype=dtype,
        ).reshape(self.fmt.frame_shape(size))
        return self._validate_generated(frame, size)

    def random(self, size, min_value=0, max_value=None, dtype=None):
        size = _require_frame_size(size)
        dtype = self._dtype(dtype)
        max_value = self._default_max(dtype) if max_value is None else max_value
        min_value = int(min_value)
        max_value = int(max_value)
        self._validate_range(min_value, max_value)
        if min_value > max_value:
            raise ValueError("min_value must be <= max_value")

        frame = self.rng.integers(
            min_value,
            max_value,
            size=self.fmt.frame_shape(size),
            dtype=dtype,
            endpoint=True,
        )
        return self._validate_generated(frame, size)

    def horizontal_ramp(self, size, start=0, stop=None, dtype=None):
        size = _require_frame_size(size)
        dtype = self._dtype(dtype)
        stop = self._default_max(dtype) if stop is None else stop
        self._validate_range(start, stop)
        row = np.linspace(start, stop, num=size.width, dtype=dtype)
        if self.fmt.number_of_color_planes == 1:
            frame = np.tile(row, (size.height, 1))
        else:
            pixels = np.repeat(
                row[:, None],
                self.fmt.number_of_color_planes,
                axis=1,
            )
            frame = np.tile(pixels[None, :, :], (size.height, 1, 1))
        return self._validate_generated(frame, size)

    def _dtype(self, dtype):
        dtype = self.fmt.dtype if dtype is None else np.dtype(dtype)
        if not np.issubdtype(dtype, np.integer):
            raise TypeError("frame dtype must be an integer dtype")
        return dtype

    def _default_max(self, dtype):
        info = np.iinfo(np.dtype(dtype))
        return min(self.fmt.sample_mask, int(info.max))

    def _validate_range(self, start, stop):
        if int(start) < 0 or int(stop) > self.fmt.sample_mask:
            raise ValueError(
                f"generated values must fit in {self.fmt.bits_per_color} bits"
            )

    def _validate_generated(self, frame, size):
        return VideoPayloadCodec(self.fmt).validate_frame(frame, size)


class VideoPayloadCodec:
    """Stateless conversion between numpy frames and AV-ST payload beats."""

    def __init__(self, fmt):
        if not isinstance(fmt, VideoFormat):
            raise TypeError("fmt must be a VideoFormat")
        self.fmt = fmt

    def validate_frame(self, frame, size):
        size = _require_frame_size(size)
        frame = np.asarray(frame)
        expected_shape = self.fmt.frame_shape(size)
        if frame.shape != expected_shape:
            raise ValueError(
                f"frame shape must be {expected_shape}, got {frame.shape}"
            )
        self._validate_integer_samples(frame, "frame")
        return frame.astype(self.fmt.dtype, copy=False)

    def frame_to_rows(self, frame, size):
        frame = self.validate_frame(frame, size)
        return [row.copy() for row in frame]

    def rows_to_frame(self, rows, size):
        size = _require_frame_size(size)
        rows = list(rows)
        if len(rows) != size.height:
            raise ValueError(f"expected {size.height} rows, got {len(rows)}")
        normalized = [self._validate_row(row, size) for row in rows]
        return np.stack(normalized).astype(self.fmt.dtype, copy=False)

    def row_to_symbols(self, row, size):
        size = _require_frame_size(size)
        row = self._as_plane_row(row, size)
        symbols = []
        pixels_per_group = self.fmt.pixels_in_parallel
        planes = self.fmt.number_of_color_planes

        for start in range(0, size.width, pixels_per_group):
            if self.fmt.color_planes_are_in_parallel:
                for pixel_offset in range(pixels_per_group):
                    pixel_index = start + pixel_offset
                    for plane in range(planes):
                        symbols.append(
                            int(row[pixel_index, plane])
                            if pixel_index < size.width
                            else 0
                        )
            else:
                for plane in range(planes):
                    for pixel_offset in range(pixels_per_group):
                        pixel_index = start + pixel_offset
                        symbols.append(
                            int(row[pixel_index, plane])
                            if pixel_index < size.width
                            else 0
                        )

        return symbols

    def symbols_to_row(self, symbols, size):
        size = _require_frame_size(size)
        symbols = [int(symbol) for symbol in symbols]
        expected_symbols = self.fmt.symbols_per_row(size)
        if len(symbols) != expected_symbols:
            raise ValueError(
                f"expected {expected_symbols} row symbols, got {len(symbols)}"
            )
        self._validate_integer_samples(
            np.asarray(symbols, dtype=object),
            "symbols",
        )

        planes = self.fmt.number_of_color_planes
        pixels_per_group = self.fmt.pixels_in_parallel
        row = np.zeros((size.width, planes), dtype=self.fmt.dtype)
        symbol_index = 0

        for start in range(0, size.width, pixels_per_group):
            if self.fmt.color_planes_are_in_parallel:
                for pixel_offset in range(pixels_per_group):
                    pixel_index = start + pixel_offset
                    for plane in range(planes):
                        sample = symbols[symbol_index]
                        symbol_index += 1
                        if pixel_index < size.width:
                            row[pixel_index, plane] = sample
                        elif sample != 0:
                            raise ValueError("non-zero padding symbol")
            else:
                for plane in range(planes):
                    for pixel_offset in range(pixels_per_group):
                        pixel_index = start + pixel_offset
                        sample = symbols[symbol_index]
                        symbol_index += 1
                        if pixel_index < size.width:
                            row[pixel_index, plane] = sample
                        elif sample != 0:
                            raise ValueError("non-zero padding symbol")

        return self._from_plane_row(row)

    def pack_row(self, row, size):
        symbols = self.row_to_symbols(row, size)
        packed = []
        for start in range(0, len(symbols), self.fmt.samples_per_beat):
            word = 0
            for index, sample in enumerate(
                symbols[start : start + self.fmt.samples_per_beat]
            ):
                word |= int(sample) << (
                    index * self.fmt.bits_per_color
                )
            packed.append(word)
        return packed

    def unpack_row(self, payload, size):
        size = _require_frame_size(size)
        payload = [int(word) for word in payload]
        expected_beats = self.fmt.beats_per_row(size)
        if len(payload) != expected_beats:
            raise ValueError(
                f"expected {expected_beats} row beats, got {len(payload)}"
            )

        max_word = (1 << self.fmt.payload_width) - 1
        symbols = []
        for word in payload:
            if word < 0 or word > max_word:
                raise ValueError(
                    f"payload word {word} does not fit in "
                    f"{self.fmt.payload_width} bits"
                )
            for index in range(self.fmt.samples_per_beat):
                symbols.append(
                    (word >> (index * self.fmt.bits_per_color))
                    & self.fmt.sample_mask
                )
        return self.symbols_to_row(symbols, size)

    def pack_frame(self, frame, size):
        return [
            word
            for row in self.frame_to_rows(frame, size)
            for word in self.pack_row(row, size)
        ]

    def unpack_frame(self, payload, size):
        size = _require_frame_size(size)
        payload = list(payload)
        beats_per_row = self.fmt.beats_per_row(size)
        expected = size.height * beats_per_row
        if len(payload) != expected:
            raise ValueError(
                f"expected {expected} frame beats, got {len(payload)}"
            )
        rows = []
        for start in range(0, expected, beats_per_row):
            rows.append(
                self.unpack_row(
                    payload[start : start + beats_per_row],
                    size,
                )
            )
        return self.rows_to_frame(rows, size)

    def frame_to_symbols(self, frame, size):
        size = _require_frame_size(size)
        frame = self.validate_frame(frame, size)
        pixels = self._frame_as_plane_pixels(frame, size)
        symbols = []
        planes = self.fmt.number_of_color_planes
        pixels_per_group = self.fmt.pixels_in_parallel

        if self.fmt.color_planes_are_in_parallel:
            for pixel in pixels:
                for plane in range(planes):
                    symbols.append(int(pixel[plane]))
            return symbols

        for start in range(0, len(pixels), pixels_per_group):
            group = pixels[start : start + pixels_per_group]
            for plane in range(planes):
                for pixel in group:
                    symbols.append(int(pixel[plane]))

        return symbols

    def symbols_to_frame(self, symbols, size):
        size = _require_frame_size(size)
        symbols = [int(symbol) for symbol in symbols]
        expected = self.fmt.frame_symbol_count(size)
        if len(symbols) != expected:
            raise ValueError(
                f"expected {expected} frame symbols, got {len(symbols)}"
            )
        self._validate_integer_samples(
            np.asarray(symbols, dtype=object),
            "symbols",
        )

        planes = self.fmt.number_of_color_planes
        pixels_per_group = self.fmt.pixels_in_parallel
        pixels = np.zeros(
            (size.width * size.height, planes),
            dtype=self.fmt.dtype,
        )
        symbol_index = 0

        if self.fmt.color_planes_are_in_parallel:
            for pixel_index in range(len(pixels)):
                for plane in range(planes):
                    pixels[pixel_index, plane] = symbols[symbol_index]
                    symbol_index += 1
        else:
            for start in range(0, len(pixels), pixels_per_group):
                group_size = min(pixels_per_group, len(pixels) - start)
                for plane in range(planes):
                    for pixel_offset in range(group_size):
                        pixels[start + pixel_offset, plane] = symbols[
                            symbol_index
                        ]
                        symbol_index += 1

        return self._frame_from_plane_pixels(pixels, size)

    def _validate_row(self, row, size):
        row = np.asarray(row)
        expected_shape = self.fmt.row_shape(size)
        if row.shape != expected_shape:
            raise ValueError(
                f"row shape must be {expected_shape}, got {row.shape}"
            )
        self._validate_integer_samples(row, "row")
        return row.astype(self.fmt.dtype, copy=False)

    def _as_plane_row(self, row, size):
        row = self._validate_row(row, size)
        if self.fmt.number_of_color_planes == 1:
            return row.reshape(size.width, 1)
        return row

    def _from_plane_row(self, row):
        if self.fmt.number_of_color_planes == 1:
            return row[:, 0]
        return row

    def _frame_as_plane_pixels(self, frame, size):
        frame = self.validate_frame(frame, size)
        if self.fmt.number_of_color_planes == 1:
            return frame.reshape(size.width * size.height, 1)
        return frame.reshape(
            size.width * size.height,
            self.fmt.number_of_color_planes,
        )

    def _frame_from_plane_pixels(self, pixels, size):
        if self.fmt.number_of_color_planes == 1:
            return pixels[:, 0].reshape(size.height, size.width)
        return pixels.reshape(
            size.height,
            size.width,
            self.fmt.number_of_color_planes,
        )

    def _validate_integer_samples(self, values, name):
        values = np.asarray(values)
        if (
            not np.issubdtype(values.dtype, np.integer)
            and values.dtype != object
        ):
            raise TypeError(f"{name} samples must be integers")
        for value in values.flat:
            if not isinstance(value, Integral):
                raise TypeError(f"{name} samples must be integers")
            value = int(value)
            if value < 0 or value > self.fmt.sample_mask:
                raise ValueError(
                    f"{name} sample {value} does not fit in "
                    f"{self.fmt.bits_per_color} bits"
                )


def _require_frame_size(size):
    if not isinstance(size, FrameSize):
        raise TypeError("size must be a FrameSize")
    return size


def compare_frames(actual, expected, tolerance=0):
    """Assert that two frames have equal shape and values within tolerance."""

    actual = np.asarray(actual)
    expected = np.asarray(expected)
    if actual.shape != expected.shape:
        raise AssertionError(
            f"frame shape mismatch: got {actual.shape}, "
            f"expected {expected.shape}"
        )
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")

    actual_obj = actual.astype(object)
    expected_obj = expected.astype(object)
    diff = np.vectorize(
        lambda left, right: abs(int(left) - int(right)),
        otypes=[object],
    )(actual_obj, expected_obj)
    mismatch = np.asarray(diff > tolerance, dtype=bool)
    if not np.any(mismatch):
        return True

    index = tuple(np.argwhere(mismatch)[0])
    coordinate = ", ".join(
        f"{axis}={value}"
        for axis, value in zip(("y", "x", "plane"), index)
    )
    raise AssertionError(
        f"frame mismatch at {coordinate}: got {actual[index]}, "
        f"expected {expected[index]}, diff={diff[index]}, "
        f"tolerance={tolerance}"
    )
