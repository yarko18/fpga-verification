<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Testbench project style

This is the project convention for a verification environment. The names below
describe roles, not an algorithm or a product, so the same structure can be
used for every IP.

Put one testbench family in `simulation/<name>/`. `<name>` identifies an
interface or integration level, for example `stream`, `core`, or `system`.
Avoid a catch-all module where unrelated interfaces share models and helpers.

```text
simulation/
  <name>/
    __init__.py
    config.py
    layout.py
    functional_model.py
    behavior_model.py
    scoreboard.py
    env.py
    test_pyuvm.py
    run_test.py
```

Additional files are welcome when they have one clear role: `sequences.py` for
reusable traffic, `registers.py` for named addresses, and `memory.py` for a
project-specific external-memory model. Do not put a second copy of a geometry
calculation or an algorithm in a test file.

## Dependency direction

Dependencies point down this stack. A lower layer must not import a higher one.

```text
run_test.py  -> config.py
test_pyuvm.py -> env.py -> scoreboard.py -> behavior_model.py
                              |                  |
                              +-> layout.py      +-> functional_model.py
                                      ^
                                  config.py
```

`config.py` may be imported everywhere. `layout.py` may be imported by models,
the environment and tests. A functional model must not import cocotb, pyuvm,
agents, a scoreboard, or a DUT handle.

## `config.py`: parameters only

`TestConfig` is the immutable, serialisable list of configuration values. It
contains HDL parameters, named cases and validation of values invalid by
themselves. It does **not** contain derived formats, frame sizes, bus objects,
model instances or helper calculations.

```python
from dataclasses import dataclass

from fpga_verification.sim import ComponentConfig, hdl_parameter


@dataclass(frozen=True)
class TestConfig(ComponentConfig):
    data_width: int = hdl_parameter(16, name="DATA_WIDTH")
    lanes: int = hdl_parameter(1, name="LANES")
    pipeline_depth: int = hdl_parameter(2, name="PIPELINE_DEPTH")

    def __post_init__(self):
        if self.data_width <= 0 or self.lanes <= 0:
            raise ValueError("data_width and lanes must be positive")


def get_test_config(case: str = "default") -> TestConfig:
    cases = {
        "default": TestConfig(),
        "wide": TestConfig(data_width=32, lanes=2),
    }
    return cases[case]
```

`run_test.py` resolves a named case before generated HDL is built.
`load_runtime_config(TestConfig)` restores that exact resolved configuration in
cocotb. Never construct a fallback `TestConfig()` in the running testbench:
that can silently make model parameters differ from HDL parameters.

## `layout.py`: derived values only

`Layout.from_config(cfg)` is the sole place that converts parameters into
formats, dimensions, masks, limits and other derived values. It is immutable.
This makes the mapping from HDL configuration to Python interpretation visible
and testable.

```python
from dataclasses import dataclass

from fpga_verification.video import VideoFormat

from .config import TestConfig


@dataclass(frozen=True)
class StreamLayout:
    stream_format: VideoFormat
    samples_per_cycle: int
    max_value: int

    @classmethod
    def from_config(cls, cfg: TestConfig) -> "StreamLayout":
        stream_format = VideoFormat(
            bits_per_color=cfg.data_width,
            number_of_color_planes=1,
            pixels_in_parallel=cfg.lanes,
        )
        return cls(
            stream_format=stream_format,
            samples_per_cycle=cfg.lanes,
            max_value=(1 << cfg.data_width) - 1,
        )
```

Do not calculate `(1 << cfg.data_width) - 1` independently in a scoreboard,
test and model. Put it in the layout once and pass the layout to all of them.

## `functional_model.py`: pure transformations

A functional model accepts domain values such as arrays, integers and
small dataclasses. It returns values and has no reset, register, clock or
packet state.

```python
class StreamFunctionalModel:
    def __init__(self, layout):
        self.layout = layout

    def process_frame(self, frame, control_value):
        return transform(frame, control_value, self.layout.max_value)
```

This class is tested with normal Python tests. It must not know how a value is
carried on Avalon-ST or when a register was written.

## `behavior_model.py`: externally visible state

The behavior model owns state that changes over the DUT lifetime. It owns its
functional helpers, accepts typed events such as a register write or input
frame, and has an explicit `reset()`.

```python
class StreamBehaviorModel:
    def __init__(self, layout):
        self.functional_model = StreamFunctionalModel(layout)
        self.reset()

    def reset(self):
        self.control_value = 0

    def process_register_write(self, address, data):
        if address == CONTROL_ADDRESS:
            self.control_value = int(data)

    def process_frame(self, frame):
        return self.functional_model.process_frame(frame, self.control_value)
```

The behavior model has no knowledge of `VIPVideoPacket`, cocotb handles or
analysis ports. It describes the IP contract, not the wire protocol. A
stateless IP still gets a behavior model with `reset()` so every environment
has the same lifecycle.

## `scoreboard.py`: protocol adapter and ordered checker

The custom scoreboard is the only layer that translates protocol objects into
model calls. It decodes an input packet, asks the behavior model for a
prediction, encodes the expected packet and adds it to the base scoreboard's
FIFO. It also forwards observed control writes in monitor order.

```python
class StreamScoreboard(BaseVIPScoreboard):
    def process_control_transaction(self, transaction):
        if transaction.kind == "write":
            self.behavior_model.process_register_write(
                transaction.address, transaction.data,
            )

    def process_input_packet(self, packet):
        frame = self.vip_input_codec.video_packet_to_frame(packet, self.size)
        expected = self.behavior_model.process_frame(frame)
        self.add_expectation(
            PacketExpectation(
                self.vip_output_codec.frame_to_video_packet(expected, self.size)
            )
        )

    def on_reset(self):
        self.size = None
        self.behavior_model.reset()
```

Keep arithmetic out of the scoreboard. One independent output stream gets one
scoreboard and one expectation queue.

## `env.py`: composition and lifecycle

`TestEnv` creates clocks, buses, BFMs, agents, codecs, one behavior model and
one custom scoreboard. `build_phase()` creates them; `connect_phase()` connects
analysis ports; `run_phase()` starts long-running clocks and monitors.

Expose short semantic helpers such as `reset()`, `send_frame()`,
`control_write()` and `stop_tasks()`. Tests should use those helpers instead of
repeating bus construction or knowing signal names.

```python
def connect_phase(self):
    self.data_agent.source_analysis_port.connect(
        self.scoreboard.data_in_export
    )
    self.data_agent.sink_analysis_port.connect(
        self.scoreboard.data_out_export
    )
    self.control_agent.analysis_port.connect(self.scoreboard.control_export)
```

Every task started by the environment must be stopped in `stop_tasks()`. The
base test calls it in a `finally` block, even after a failed assertion.

## `test_pyuvm.py`: contract-focused scenarios

Define one base `uvm_test` that loads the runtime config, constructs `TestEnv`,
performs reset, calls a test-specific `body()`, drains the scoreboard and stops
tasks. Individual tests then state only the scenario and its observable result.

```python
class BaseStreamTest(uvm_test):
    def build_phase(self):
        self.cfg = load_runtime_config(TestConfig)
        self.env = TestEnv("env", self, cocotb.top, self.cfg)

    async def run_phase(self):
        self.raise_objection()
        try:
            await self.env.reset()
            await self.body()
            await self.env.scoreboard.drain()
        finally:
            self.env.stop_tasks()
            self.drop_objection()
```

Keep a small set of orthogonal tests: reset/default behaviour, control updates,
one ordinary transaction, boundaries, multiple in-flight transactions and
ready/valid randomisation. A test name describes a contract, not implementation
details.

## `run_test.py`: thin human-readable entry point

The runner selects a simulator and invokes a library wrapper. It may contain
documented simulator workarounds, but it does not calculate layout or expected
data and must not duplicate testbench configuration.

```python
import os
from pathlib import Path

from fpga_verification.sim.runners import run_intel_component_test
from .config import get_test_config


if __name__ == "__main__":
    run_intel_component_test(
        project_root=Path(__file__).resolve().parent,
        component_file="../../src/component_hw.tcl",
        hdl_toplevel="component",
        test_module="stream.test_pyuvm",
        config=get_test_config(os.getenv("FPGA_VERIFICATION_CONFIG_CASE")),
        enable_questa_acc=True,
    )
```

Use `SIM=verilator` for the default fast path and `SIM=questa` when interactive
debugging or simulator-specific generated libraries are needed. The complete
runner reference is in [Simulation runners](../sim/runners.md).

## Review checklist

- Configuration values live only in `config.py`; derived values live only in
  `layout.py`.
- The functional model has no simulator or protocol imports.
- The behavior model owns state and provides `reset()`.
- The scoreboard adapts packets and transactions but does not implement the
  algorithm.
- The environment is the only composition root for agents, models and BFMs.
- Each test drains the checker and stops background tasks in `finally`.
- The runner stays small enough that a reviewer can understand its invocation
  without reading the environment.
