<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Memory-backed streaming component

Consider a component with a packet stream, an Avalon-MM control port, external
memory masters, two clock domains and an interrupt. Several coefficient arrays
live in external memory; scalar coefficients and mode selection live in
registers. One command can also update a coefficient array from captured frames.

The case study focuses on keeping all observable state coherent.

## Separate four kinds of state

Treat these state groups explicitly:

1. register state owned by the behavior model;
2. coefficient arrays stored in the memory model;
3. transient command state and completion events;
4. protocol context such as the active control geometry.

Reset may affect these groups differently. For example, registers and pending
commands can reset while external memory contents survive. `on_reset()` must
follow the RTL contract rather than clearing every Python object indiscriminately.

## Keep memory and prediction coherent

Use one helper whenever a test installs a coefficient array:

```python
def set_coefficient(self, address, values):
    self.memory.write(address, values.tobytes())
    self.behavior_model.set_coefficient(address, values)
```

Updating only memory or only the behavior model creates a false comparison.
Runtime address changes should select the same array in both the DUT-visible
memory map and the prediction state.

## Model commands in phases

A long-running update command often has three distinct model operations:

- predict the result without changing state;
- compare memory, status and interrupt outputs from the DUT;
- commit the checked result as the next active coefficient state.

Keeping prediction and commit separate prevents the model from moving ahead of
an operation that has not completed.

## Useful scenarios

- stream passthrough and active modes;
- each coefficient group independently and in combination;
- default and runtime memory addresses;
- command completion, status and interrupt acknowledgement;
- randomized memory latency and stream backpressure;
- unsupported frame geometry followed by a valid frame;
- reset during an in-flight stream packet;
- reset-state versus retained-memory behavior.
