<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Architecture

`fpga-verification` separates values, protocol transport, prediction and
simulation launch so the same calculation can be checked without a simulator,
inside cocotb, and later against hardware.

```text
data and numeric formats      numpy values, frames, fixed-point words
protocol layer                packets, codecs and protocol history
simulation layer              BFMs, agents, monitors and scoreboards
launch layer                  RTL, generated-component and system runners
hardware layer                persistent System Console access
```

Dependencies point downward. Neutral data objects do not know about clocks or a
DUT. Protocol codecs do not retain application state. Simulation components add
handshaking, observation, ordering and reset behavior.

## Verification path

For one streaming path:

```text
sequence -> driver -> input bus -> DUT -> output bus -> monitor
                         |                         |
                    input monitor                 |
                         +------> scoreboard <-----+
                                      |
                               behavior model
                                      |
                          optional functional model
```

- The codec translates between Python objects and wire symbols.
- The agent drives and observes a protocol.
- The custom scoreboard translates protocol events into model operations.
- The behavior model predicts externally visible component behavior.
- `BaseVIPScoreboard` compares output against a strict FIFO of expectations.

## Composition boundary

The pyuvm environment is normally the composition root. It creates clocks,
buses, BFMs, agents, models and scoreboards, then connects their analysis ports.
Tests interact with short semantic helpers such as `reset()`, `send_frame()` and
`control_write()` rather than constructing buses themselves.

A separate behavior model is a recommendation, not a library requirement. It is
valuable when the component has registers, modes, history, memory selection or
reset state. A small stateless converter may call a pure functional model
directly from its scoreboard; teams may still keep an empty-lifecycle behavior
object for structural consistency.

## Ownership summary

| Layer | Owns | Must not own |
| --- | --- | --- |
| Functional model | Pure calculation and conversion | Protocol order, registers, clocks, reset |
| Behavior model | Visible state and typed component operations | VIP packet decoding and analysis ports |
| Custom scoreboard | Protocol context and input-to-expectation mapping | Application arithmetic and long-lived state |
| Base scoreboard | Ordered comparison, reset epochs, completion, failures | Component prediction |
| Environment | Construction, connections and task lifecycle | Expected-result algorithms |
| Test | Scenario and observable assertions | Duplicated bus setup or model calculation |

Use [Project style](testbench-style.md) for file ownership and
[Modelling DUT behavior](modeling.md) for state and prediction rules.
