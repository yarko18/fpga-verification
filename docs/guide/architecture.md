<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Architecture

The library is split by responsibility so the same data and prediction code
can be used without a simulator, inside cocotb, and later against real
hardware.

```text
data and codecs          Python/numpy values, frames, protocol packets
        |
simulation components   buses, BFMs, agents, monitors, scoreboards
        |
runners                  simulator and generated-IP launch
        |
hardware access          persistent System Console session
```

The lower layers do not know about clocks or a DUT. Simulation components add
handshaking, reset, ordering, logging, and observation. A project-specific
testbench supplies the behavior of the IP being checked.

## A verification path

For a streaming IP, one complete path normally looks like this:

```text
sequence -> driver -> input bus -> DUT -> output bus -> monitor
                         |                         |
                    input monitor                 |
                         +------> scoreboard <-----+
                                      |
                               behavior model
                                      |
                          optional functional models
```

The codec translates between Python objects and wire symbols. The agent drives
and observes the protocol. The scoreboard preserves ordering and turns
semantic model results into explicit output expectations.

## Composition rule for an IP testbench

Use the pyuvm `Env` as the composition root:

- create one explicit `*BehaviorModel` for every IP;
- let that behavior model create any pure `*FunctionalModel` helpers it needs;
- pass the behavior model into the custom scoreboard;
- share the same behavior model with other scoreboards or environment helpers
  only when they represent the same DUT state;
- reset state through the behavior model API instead of changing its fields
  from the environment.

The behavior model remains explicit even when it is currently stateless. This
makes dependency injection, reset lifecycle, and future state changes uniform
across testbenches.

```python
class MyIPBehaviorModel:
    def __init__(self, cfg, functional_model=None):
        self.cfg = cfg
        self.functional_model = functional_model or MyIPFunctionalModel(cfg)
        self.reset()

    def reset(self):
        ...


class MyEnv(uvm_env):
    def build_phase(self):
        self.model = MyIPBehaviorModel(self.cfg)
        self.scoreboard = MyIPScoreboard(
            "scoreboard",
            self,
            source_fmt=self.source_fmt,
            sink_fmt=self.sink_fmt,
            model=self.model,
        )
```

This is a composition convention, not a required library base class. A simple
IP may have no separate functional model at all.

## Responsibility boundaries

`FunctionalModel`
: Performs pure calculation or conversion. It has no protocol ordering,
  register lifecycle, memory addresses, or reset state.

`BehaviorModel`
: Describes IP-visible behavior and state transitions. It owns functional
  helpers and exposes typed operations appropriate to the IP.

Custom scoreboard
: Adapts observed packets or transactions to typed model calls. It handles
  protocol context and creates `PacketExpectation` objects.

`BaseVIPScoreboard`
: Compares the observed output with queued expectations in strict order. It
  does not predict IP behavior.

Avoid forcing every model into a single `process_packet()` interface. Control
transactions, video frames, and completion events can have different semantic
meaning. The scoreboard is the right place to dispatch protocol objects to
typed behavior-model operations.

The [library overview notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/00_library_overview.ipynb)
maps the package layers. The
[VIP verification notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/09_vip_verification_components.ipynb)
shows how the simulation-side pieces connect.

Next: [start a simulation](../sim/runners.md).
