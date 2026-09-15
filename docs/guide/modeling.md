<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Modeling DUT behavior

A verification environment needs more than a Python version of an algorithm.
It must also describe register state, packet order, reset behavior, and the
mapping from input traffic to expected output traffic. These tasks are easier
to maintain when they are split into small layers.

```text
protocol packets and control transactions
                    |
             custom scoreboard
                    |
              behavior model
                    |
        one or more functional models
                    |
          values, arrays, and results
```

The layers have clear boundaries:

- a functional model performs a pure calculation;
- a behavior model represents the visible state and behavior of the DUT;
- a custom scoreboard adapts protocol objects to model operations;
- `BaseVIPScoreboard` checks ordered output expectations.

`FunctionalModel` and `BehaviorModel` are naming conventions. The library does
not require a common base class for them. Their public operations should match
the work performed by the DUT.

## Describe the interface layout

Start with one immutable layout object derived from the test configuration. It
can hold input and output video formats, frame limits, numeric formats, and
other parameters that change the meaning of data. The environment can pass the
same layout to agents, codecs, and models.

This avoids repeated calculations and makes configuration errors visible
before traffic starts. It is also useful when input and output interfaces have
different symbol widths or pixels per beat.

## Keep the functional model pure

A functional model accepts domain values such as arrays, frame sizes, or
numeric parameters. It returns a value or a small result object. It should not
know about cocotb, pyuvm, clocks, resets, bus transactions, or VIP packet
classes.

```python
class StreamFunctionalModel:
    def __init__(self, layout):
        self.layout = layout

    def process_video_frame(self, frame, coefficient):
        return calculate_output(frame, coefficient, self.layout)
```

The same object can then be used in fast Python unit tests, in simulation, or
in a software tool. A pure model is deterministic: the same inputs and
configuration produce the same result.

If a calculation has several outputs, return a dataclass instead of changing
hidden object state. This makes intermediate values available to tests without
mixing them with the DUT lifecycle.

## Put DUT state in the behavior model

The behavior model owns state that changes while the DUT runs. Typical state
includes register values, operating modes, history windows, active
coefficients, and counters. It creates and owns any functional models that it
needs.

```python
class StreamBehaviorModel:
    def __init__(self, layout):
        self.functional_model = StreamFunctionalModel(layout)
        self.reset()

    def reset(self):
        self.mode = DEFAULT_MODE
        self.coefficient = DEFAULT_COEFFICIENT

    def process_register_write(self, address, data):
        ...

    def process_video_frame(self, frame):
        expected = self.functional_model.process_video_frame(
            frame,
            self.coefficient,
        )
        return VideoPacketResult.exact(expected)
```

Use typed operations that express real DUT actions. For example,
`process_register_write()`, `process_video_frame()`,
`process_control_geometry()`, and `process_user_payload()` give useful
boundaries. A universal `process_packet()` method would couple the model to the
wire protocol and hide the meaning of each operation.

A behavior model may still be stateless. Give it an explicit `reset()` method
so all environments use the same lifecycle and future state can be added
without changing their structure.

## Adapt protocols in the custom scoreboard

The custom scoreboard is the boundary between protocol objects and the
behavior model. It performs work such as:

- dispatching control, user, and video packets;
- converting a video packet to a frame with the active input geometry;
- translating an observed control-bus write to
  `process_register_write(address, data)`;
- converting a model result back to an output packet;
- creating zero or more `PacketExpectation` objects in output order.

Keep arithmetic and long-lived DUT state out of this layer. The custom
scoreboard should contain protocol context and small conversion rules.

Control-bus transactions must be applied in the order in which their monitor
publishes them. This gives the behavior model the same register state that the
DUT had when it accepted each input packet.

## Compose the objects in the environment

The pyuvm environment is the composition root. It creates one behavior model
and injects it into the custom scoreboard.

```python
class StreamEnv(uvm_env):
    def build_phase(self):
        self.layout = StreamLayout.from_config(self.cfg)
        self.behavior_model = StreamBehaviorModel(self.layout)
        self.scoreboard = StreamScoreboard(
            "scoreboard",
            self,
            source_fmt=self.layout.input_format,
            sink_fmt=self.layout.output_format,
            behavior_model=self.behavior_model,
            clock=self.clock,
            reset=self.reset_signal,
        )
```

Share this behavior model with another checker only when both components
represent the same DUT state. Do not create separate stateful models for the
data path and control path, because they can move to different states.

Use one `BaseVIPScoreboard` instance for each independent output stream. Each
instance owns one expectation queue, protocol context, failure state, and frame
counters.

## Treat reset as a state transition

When reset is asserted, `BaseVIPScoreboard` clears pending expectations and its
output protocol context. It then calls the custom `on_reset()` hook. The custom
scoreboard should clear its input context and call the behavior model's
`reset()` method.

Decide explicitly which state survives reset. For example, external memory may
keep its contents even when registers and temporary windows return to their
defaults. The Python model should follow the RTL contract.

## Test each boundary

The same split gives a useful test order:

1. Test functional models with normal Python unit tests.
2. Test behavior-model modes, register writes, history, and reset without a
   simulator.
3. Test the custom scoreboard's packet dispatch and expectation creation.
4. Run integration tests with agents, monitors, and the RTL DUT.

Errors found in the first three steps are faster to reproduce and easier to
understand. The full simulation can then focus on handshake, timing, and RTL
integration.

The
[VIP verification notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/09_vip_verification_components.ipynb)
shows the reusable library components used around these project models.

Next: [turn model results into ordered VIP checks](vip-verification.md).
