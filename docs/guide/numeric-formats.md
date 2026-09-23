<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Numeric formats

Numeric helpers make Python and numpy values match finite hardware words.
They are independent of cocotb and useful in functional models, codecs and
unit tests that need exact raw representations.

## Unsigned words

`UIntFormat` masks values to a selected width and chooses a suitable unsigned
numpy storage type. Values outside the range wrap through the raw word mask.

```python
from fpga_verification.formats import UIntFormat, unsigned_storage_dtype

mono10 = UIntFormat(width=10)
raw_pixels = mono10.array([0, 1023, 1024, -1])

assert raw_pixels.tolist() == [0, 1023, 0, 1023]
print(raw_pixels.dtype)
print(hex(mono10.mask))

for width in (1, 9, 17, 33):
    print(width, unsigned_storage_dtype(width))
```

`zeros()`, `full()`, `array()` and `wrap()` preserve the selected storage
representation. Use them instead of a bare numpy constructor when the bit
width is part of the test contract.

## Fixed-point words

`QFormat(qi, qf, signed)` describes a stored fixed-point word: `qi` integer
bits, `qf` fractional bits, and a signed or unsigned two's-complement
interpretation. It exposes raw, scaled-integer and floating-point conversions.

```python
from fpga_verification.formats import QFormat

unsigned = QFormat(qi=2, qf=0, signed=False)
signed = QFormat(qi=2, qf=0, signed=True)

print(unsigned.qraw_to_int(0b11))  # 3
print(signed.qraw_to_int(0b10))    # -2

q = QFormat(qi=3, qf=4, signed=True)
print(q.min_int, q.max_int)
print(q.min_float, q.max_float)
```

The distinction matters: a raw word is a bit pattern, an integer is its signed
or unsigned interpretation, and a float includes the fractional scale.

```python
q = QFormat(qi=3, qf=4, signed=False)
raw = q.float_to_qraw(3.75)
assert raw == 60
assert q.qraw_to_float(raw) == 3.75
```

## Arrays, filling and random data

All conversions accept scalars and numpy-compatible arrays.

```python
q = QFormat(qi=3, qf=2, signed=True)
raw = q.float_to_qraw([1.25, -1.0, 7.75])
restored = q.qraw_to_float(raw)

print(raw.tolist())
print(restored.tolist())
print(q.zeros(4))
print(q.ones(4))
print(q.full(4, 1.25))
print(q.full(4, 1, raw=True))
```

`randomize(raw=True)` samples raw bit patterns uniformly and returns the
unsigned storage dtype. `randomize(raw=False)` samples numeric values in the
representable float range; values are quantised only when converted through
`float_to_qraw()`.

## Saturation, wrapping and quantisation

Float conversion saturates by default. Set `saturate=False` only when hardware
semantics explicitly wrap.

```python
q = QFormat(qi=3, qf=2, signed=True)

saturated = q.float_to_qraw([10.0, -10.0])
wrapped = q.float_to_qraw([10.0, -10.0], saturate=False)
quantized = q.float_to_qraw([0.49, -0.49])

print(q.qraw_to_float(saturated).tolist())
print(q.qraw_to_float(wrapped).tolist())
print(q.qraw_to_float(quantized).tolist())
```

Document the chosen overflow rule in the functional model. A silent choice
between saturation and wrapping is a common source of model-versus-RTL
mismatches.

## Multiplication

`multiply()` operates on scaled integer representations. It can shift the
product to a requested fractional width but does not select an output word
width or apply the final overflow policy.

```python
left = QFormat(qi=3, qf=2, signed=False)
right = QFormat(qi=2, qf=4, signed=False)
raw_product = left.multiply(10, right, 10)

result_format = QFormat(qi=5, qf=6, signed=False)
print(result_format.qraw_to_float(raw_product))
```

Create the intended output format explicitly, then choose saturation or masking
at the hardware boundary. Keeping that final decision visible makes a
functional model reviewable.

Next: [use these representations in a behavior model](modeling.md).
