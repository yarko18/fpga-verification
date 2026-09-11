<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Numeric formats

Numeric helpers are the final, lowest-level part of the story. Use them when a
test must match the exact raw words stored in hardware rather than only the
protocol around those words.

## Unsigned words

`UIntFormat` masks Python or numpy values to a configurable width and selects
the smallest suitable unsigned numpy dtype.

```python
pixel = UIntFormat(width=10)
raw = pixel.array([0, 1023, 1024, -1])
assert raw.tolist() == [0, 1023, 0, 1023]
```

## Fixed-point words

`QFormat` converts numeric values, scaled integers, and stored two's-complement
words. It exposes the scale, mask, representable range, and storage dtype.

```python
sample = QFormat(qi=3, qf=2, signed=True)
raw = sample.float_to_qraw([1.25, -1.0])
values = sample.qraw_to_float(raw)
```

Conversions saturate by default; disabling saturation wraps through the raw
word mask. Multiplication operates on scaled integer representations and can
shift the result to a requested fractional width. The caller still chooses
the final output format and saturation policy.

See the
[numeric formats notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/01_numeric_formats.ipynb)
for constructors, arrays, quantization, wrapping, and multiplication.
