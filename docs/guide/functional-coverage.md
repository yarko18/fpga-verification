<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Functional coverage

Functional coverage records which meaningful scenarios a simulation observed.
It complements assertions and scoreboards: a scoreboard says whether an
observed result is correct, while coverage says whether the intended input,
state and interaction classes occurred at all.

The optional
[`cocotb-coverage`](https://github.com/mciepluc/cocotb-coverage) integration is
available on Python 3.11 and newer:

```bash
python -m pip install "fpga-verification[functional-coverage]"
```

Version 2.0 is used because it supports cocotb 2.x. It can define coverpoints
and crosses, report hit bins, export XML or YAML, and merge exported runs.

Enable coverage declared by a testbench through its normal runner:

```bash
python run_test.py --coverage
```

Coverage can be collected across a parameter matrix as well:

```bash
python run_test.py --matrix --coverage --test CombinedPacketTest -j max
```

Each matrix worker writes an isolated XML database. The parent runner preserves
those databases under `logs/coverage/matrix/`, merges them into
`logs/functional_coverage.xml`, and enforces declared requirements after an
unfiltered full run. A run using `--test` still writes and merges its report but
does not enforce suite-level closure thresholds; this lets an individual test
report its contribution without failing because other tests' bins are absent.
`--matrix` may be combined with `--coverage`; it cannot be combined with
`--param-preset`, because a matrix already owns the resolved configuration of
every child process.

Without the flag, the optional library is not imported and the same cocotb
tests run only their correctness checks.

## Where coverage belongs

Do not put DUT-specific bins in a generic BFM or protocol agent. A BFM owns bus
timing and a monitor owns accepted transactions; neither knows which values or
crosses are important for a particular IP.

For a structured pyuvm testbench, keep the IP-specific wrapper beside the
testbench, normally in `simulation/<name>/coverage.py`. Instantiate it in the
environment and connect it to the same monitor analysis ports used by
scoreboards and metrics:

```text
monitor ── accepted transaction ──┬──> scoreboard
                                  ├──> coverage collector
                                  └──> performance metrics
```

This keeps sampling aligned with actual protocol acceptance. Reusable
protocol-only coverage may be packaged as an optional subscriber, but the
environment still chooses whether to connect it. Scenario coverage that
combines configuration, control state, input and output usually belongs to the
IP-specific collector.

The reusable structure has four distinct responsibilities:

1. `fpga_verification.sim.analysis.Subscriber` describes the plain-Python
   `write(item)` contract used by coverage collectors; it does not depend on
   pyuvm.
2. `CoverageGroup`, `CoverageScope`, and `FunctionalCoverageSession` provide
   sampling namespaces and one simulation-wide lifecycle on top of
   `cocotb-coverage`.
3. Protocol packages can provide reusable collectors such as
   `protocols.avalon_st.AvalonSTCycleCoverage` and
   `altera.video.VIPPacketCoverage`.
4. An IP coverage wrapper exposes domain methods such as `sample_input()` and
   `sample_output()`. Classic cocotb tests call them directly; a pyuvm
   environment connects native analysis ports to those same methods through
   `fpga_verification.sim.analysis.pyuvm.AnalysisImp`.

The same coverage model can therefore be driven by either test style, while
only the UVM environment needs a pyuvm adapter. The coverpoint implementation
is from `cocotb-coverage`; the lifecycle is supplied by `fpga-verification`.

## Parameter coverage

`ParameterCoverage` reuses the domains already declared for matrix planning:

```python
scope = CoverageScope("top.my_ip.parameters")
parameters = ParameterCoverage(
    scope,
    cfg,
    names=("operation", "width", "lanes"),
    crosses={"configuration": ("operation", "width", "lanes")},
    ignore_illegal=True,
)
parameters.write(cfg)
```

With `ignore_illegal=True`, the cross calls the same `ComponentConfig`
constructor used by the matrix planner and excludes combinations rejected by
`__post_init__`. A random matrix therefore reports `selected/legal`, rather
than dividing by an impossible Cartesian product. A model can nominate the
configuration cross through `report_bins`; after merge the runner prints a
compact table containing only bins with non-zero hits. The XML remains the
authoritative complete database and includes both hit and missing bins.

For a direct cocotb test, a decorated ordinary Python sampling function is
enough:

```python
from cocotb_coverage.coverage import CoverCross, CoverPoint


@CoverPoint("top.adder.a_negative", xf=lambda a, b: a < 0,
            bins=[False, True])
@CoverPoint("top.adder.b_negative", xf=lambda a, b: b < 0,
            bins=[False, True])
@CoverCross("top.adder.sign_cross",
            items=["top.adder.a_negative", "top.adder.b_negative"])
def sample_adder(a, b):
    pass
```

Call the function only at the chosen sampling event, after the transaction was
accepted or the registered result became observable.

## Avalon-ST cycle and packet coverage

`AvalonSTCycleCoverage` is a sidecar observer. It samples the raw `ready` and
`valid` pins on rising clock edges and does not change the source, sink, or
monitor BFM. It records the four pin combinations and, for each accepted beat,
the number of cycles that beat waited for qualified `ready`. The default wait
bins are 0, 1, 2–3, 4–7 and 8 or more cycles. `ready_latency=1` applies the
previous cycle's `ready` value when deciding whether a beat was accepted.
This collector measures traffic; protocol assertions or a checker must still
report violations such as dropping `valid` before a stalled beat is accepted.

```python
import cocotb
from cocotbext.avalon import AvalonSTBus
from fpga_verification.protocols.avalon_st import AvalonSTCycleCoverage
from fpga_verification.sim.coverage import (
    CoverageScope,
    get_functional_coverage_session,
)

input_bus = AvalonSTBus.from_prefix(dut, "din")
session = get_functional_coverage_session("top")
cycle_coverage = (
    None
    if session is None
    else session.model(
        "input_stream",
        lambda: AvalonSTCycleCoverage(
            CoverageScope("top.input_stream"),
            ready_latency=0,
        ),
    )
)
cycle_monitor = (
    None
    if cycle_coverage is None
    else cocotb.start_soon(
        cycle_coverage.monitor(input_bus, dut.clk, reset=dut.reset)
    )
)
# Cancel cycle_monitor in this test's finally block when it is not None.
```

Obtain the model through `FunctionalCoverageSession.model()` as shown so all
tests in the simulator process contribute to one set of bins. Each test starts
and cancels its own bus observer; the runner checks the suite's requirements
only for an unfiltered run.

Cancel `cycle_monitor` during test teardown. Reset cycles are excluded and
clear a pending wait. If an interface omits `ready` or `valid`, the observer
treats the missing signal as asserted and excludes unreachable cycle states;
backpressure coverage is omitted when `ready` is absent. For a present signal
that is tied off by a particular IP, pass only the applicable
`expected_states` and `backpressure_bins`.

For example, to close only the states reachable when `ready` is tied high, use
`expected_states=("ready_only", "ready_valid")` and
`backpressure_bins={"none": (0, None)}`.
Set `include_backpressure=False` when the interface profile has no meaningful
backpressure behavior to measure.

`VIPPacketCoverage` records both broad categories (`video`, `control`, `user`,
`ancillary`) and exact packet types. The exact user bins are `user1` through
`user8`, matching the packet types represented by `VIPPacketType`. Pass
`expected_types` when a specific VIP/IP profile supports only a subset; when
omitted, exact types are derived from `expected_kinds`.

Cycle coverage and packet coverage answer different questions. The former
samples every clock; the latter should be connected to accepted, decoded packet
observations. Keep field ranges, control/video relationships, and IP-specific
requirements in the project coverage model, where the supported feature profile
is known.

## Reports and requirements

The coverage model exports an XML report and a small JSON policy file. A model
may set independent requirements for its layers: for example, require 100% of
the expected protocol packet kinds while keeping a random parameter cross
informational. In a normal run the runner checks the final process-wide report;
in a matrix run it checks the merged report. This avoids failing early jobs for
coverage that is intended to accumulate across configurations.

Coverage is intentionally an optional dependency, so users that only need
runners and BFMs do not import it. `--coverage` validates Python 3.11+ and the
`fpga-verification[functional-coverage]` extra before simulation.

See the
[registered-adder demo](https://github.com/yarko18/fpga-verification/tree/main/examples/adder_coverage)
for a complete small run that reaches and checks a declared coverage target.
