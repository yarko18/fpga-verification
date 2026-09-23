<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Tutorial: verify a stream pipeline

This tutorial builds the `stream_pipeline` example shipped with the repository.
The RTL is a one-entry elastic stage, and the tutorial follows its complete
verification path.

## The observable contract

The component has one input and one output Intel Avalon-ST packet stream. Its
contract is:

1. preserve packet order and packet type;
2. preserve control geometry and user payloads;
3. preserve every video sample;
4. retain valid output while the sink applies backpressure;
5. discard in-flight state on reset.

The verification path is:

```text
VIPSequence -> source driver -> input register -> sink monitor
                    |                                |
             source monitor ----------------> scoreboard
                                                   |
                                            behavior model
```

## Share one configuration

[`config.py`](https://github.com/yarko18/fpga-verification/blob/main/examples/stream_pipeline/simulation/vip/config.py)
declares HDL parameters and runtime-only frame dimensions. The runner passes
`cfg.to_parameters()` to the RTL compiler and serialises the complete object for
cocotb. The running test restores it with `load_runtime_config(TestConfig)`.

This prevents a test from silently interpreting a stream differently from the
compiled RTL.

## Derive the interface layout once

[`layout.py`](https://github.com/yarko18/fpga-verification/blob/main/examples/stream_pipeline/simulation/vip/layout.py)
converts the configuration into one `VideoFormat` and one `FrameSize`. Agents,
codecs, models and tests share those objects. No later layer recalculates bus
width or frame geometry.

## Keep calculation separate from lifecycle

The example's functional model returns an independent copy of the input frame.
The behavior model converts that value into `VideoPacketResult.exact()` and has
an explicit `reset()` even though it currently retains no state.

[`tests/test_models.py`](https://github.com/yarko18/fpga-verification/blob/main/examples/stream_pipeline/tests/test_models.py)
checks both boundaries as ordinary Python, without compiling RTL.

For a component with a calculation, replace only the pure operation:

```python
class StreamFunctionalModel:
    def __init__(self, coefficient_0, coefficient_1, maximum):
        self.coefficient_0 = coefficient_0
        self.coefficient_1 = coefficient_1
        self.maximum = maximum

    def process_frame(self, frame):
        value = frame * self.coefficient_0 + self.coefficient_1
        return value.clip(0, self.maximum)
```

Register timing and reset still belong in the behavior model, not in this pure
calculation.

## Adapt packets in the scoreboard

[`scoreboard.py`](https://github.com/yarko18/fpga-verification/blob/main/examples/stream_pipeline/simulation/vip/scoreboard.py)
is the protocol boundary. It passes control and user packets through exactly. A
video packet is decoded with the active geometry, sent to the behavior model,
encoded again, and queued as a `PacketExpectation`.

The base scoreboard owns output ordering, comparison, sticky failures, reset
epochs and completion. The custom scoreboard owns only the mapping specific to
this component contract.

## Compose and connect in the environment

[`env.py`](https://github.com/yarko18/fpga-verification/blob/main/examples/stream_pipeline/simulation/vip/env.py)
creates the clock, buses, `VIPAgent`, behavior model and scoreboard. Its
`connect_phase()` wires both analysis paths:

```python
self.data_agent.source_analysis_port.connect(self.scoreboard.data_in_export)
self.data_agent.sink_analysis_port.connect(self.scoreboard.data_out_export)
```

Semantic helpers keep tests independent from signal names: `reset()`,
`send_packets()`, `drain()` and `stop_tasks()`.

## State the scenario in the test

[`test_pyuvm.py`](https://github.com/yarko18/fpga-verification/blob/main/examples/stream_pipeline/simulation/vip/test_pyuvm.py)
contains a base lifecycle and one contract-focused scenario. The scenario builds
control, user and video packets, sends them as one ordered sequence, and relies
on the scoreboard for output checking.

The `finally` block always cancels BFMs and the clock. A failed comparison must
not leave simulator tasks running.

## Launch through the runner

[`run_test.py`](https://github.com/yarko18/fpga-verification/blob/main/examples/stream_pipeline/simulation/vip/run_test.py)
selects the source directory, top-level module, test module and resolved
configuration. It contains no stimulus and no expected data.

After the example passes, useful extensions are:

- enable source and sink timing randomisation;
- insert two or more packets before waiting for output;
- assert reset while a packet is pending;
- add a register interface and move its state into the behavior model;
- replace the identity functional model with an independently tested transform.
