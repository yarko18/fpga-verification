<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Stateful frame transform

Consider a stream component with manual and automatic modes. In manual mode two
registers select `coefficient_0` and `coefficient_1`. In automatic mode the
component derives an effective coefficient set from a configurable history
window of earlier frames.

The verification problem is register state, frame history and output timing.

## Split calculation from time

The functional model accepts a frame and a resolved coefficient set. It returns
the transformed frame and any intermediate bounds useful for diagnostics. It
does not own the history window or know when registers were written.

The behavior model owns:

- current mode;
- manual coefficient registers;
- configured history depth;
- the rolling history window;
- the last resolved values;
- reset defaults.

For every input frame it returns an explicit `VideoPacketResult`.

## Warm-up is still a contract

Before the history window is full, the component produces an output packet but
its data is not yet defined. Represent that with a shape expectation:

```python
if len(self.history) < self.history_depth:
    result = VideoPacketResult.shape(reason="history warm-up")
else:
    result = VideoPacketResult.exact(expected, tolerance=allowed_error)
```

`SHAPE` verifies packet type and output length; it is not a skipped comparison.
Once the window is ready, exact checking begins without changing the scoreboard
architecture.

## Control ordering

An Avalon-MM monitor publishes accepted register writes to the scoreboard. The
scoreboard forwards them to the same behavior model used for frame prediction.
This is essential: a model updated when the test *requests* a write can get
ahead of a DUT that accepted it later.

## Useful scenarios

- reset defaults and both modes;
- coefficient boundaries;
- first exact result after warm-up;
- several history depths;
- frames queued while earlier outputs are still pending;
- randomized ready/valid timing;
- reset with a pending frame, followed by clean recovery;
- a separate sustained-throughput scenario.
