<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Modelling DUT behavior

Prediction has three distinct concerns:

```text
protocol objects -> custom scoreboard -> behavior model -> functional model
```

The split is useful when each boundary can be explained and tested
independently. Do not create wrapper classes merely to satisfy a diagram.

## Functional model: values in, values out

A functional model accepts arrays, integers or small dataclasses and returns new
values. It has no clocks, resets, register timing, packet order or analysis
ports.

```python
class TransformFunctionalModel:
    def __init__(self, maximum):
        self.maximum = maximum

    def process_frame(self, frame, coefficient_0, coefficient_1):
        value = frame * coefficient_0 + coefficient_1
        return value.clip(0, self.maximum)
```

Use ordinary Python tests for boundaries, rounding, saturation and randomized
input. If a calculation returns several diagnostic values, return a dataclass
instead of placing them in hidden mutable state.

## Behavior model: visible state and time

Add a behavior model when prediction depends on accepted register writes,
operating mode, frame history, command completion or reset. Its public methods
should name component operations rather than protocol containers:

```python
class TransformBehaviorModel:
    def __init__(self, functional_model):
        self.functional_model = functional_model
        self.reset()

    def reset(self):
        self.coefficient_0 = 1
        self.coefficient_1 = 0

    def process_register_write(self, address, data):
        ...

    def process_video_frame(self, frame):
        expected = self.functional_model.process_frame(
            frame,
            self.coefficient_0,
            self.coefficient_1,
        )
        return VideoPacketResult.exact(expected)
```

Avoid a universal `process_packet()` method. Control writes, frames, external
memory updates and completion events have different semantic meaning.

## Custom scoreboard: protocol adaptation

The custom scoreboard is the only layer that needs both protocol objects and
the behavior model. It may:

- dispatch control, user and video packets;
- decode a video payload using active control geometry;
- forward an accepted control-bus write;
- encode a model result as an output packet;
- create zero or more ordered expectations.

Keep arithmetic and long-lived component state out of this layer.

## Explicit output policy

One input video packet should result in an explicit policy:

- `VideoPacketResult.exact(value, tolerance=...)` when content is predictable;
- `VideoPacketResult.shape(reason=...)` when a packet must exist but its content
  is not defined;
- `VideoPacketResult.drop(reason=...)` when no packet should be produced.

Warm-up periods, disabled modes and malformed-input recovery then become visible
contracts instead of implicit exceptions in a scoreboard.

## Reset and external state

Decide which state resets and which survives. External memory can retain
coefficient arrays while registers and pending history return to defaults. The
behavior model, memory BFM and scoreboard protocol context do not necessarily
share one reset policy.

When a test writes model-visible data directly into a memory BFM, update the
prediction state through the same environment helper. Otherwise the DUT and
model can consume different coefficient sets.

## Test the boundaries

1. Test functional calculations without a simulator.
2. Test behavior modes, register writes, history and reset as ordinary Python.
3. Test scoreboard packet dispatch and expectation creation.
4. Use RTL simulation for handshake, timing and integration.

The [stateful transform](../case-studies/stateful-transform.md) and
[memory-backed component](../case-studies/memory-backed-component.md) show how
these rules scale to larger testbenches.
