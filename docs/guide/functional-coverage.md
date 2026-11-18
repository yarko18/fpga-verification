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
`logs/functional_coverage.xml`, and only then enforces the declared coverage
requirements. `--matrix` may be combined with `--coverage`; the incompatible
combination is `--matrix` with `FPGA_VERIFICATION_CONFIG_CASE`, because a
matrix already owns the resolved configuration of every child process.

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

1. `fpga_verification.sim.analysis` provides a plain-Python `Subscriber` and
   `AnalysisPort`; neither depends on pyuvm.
2. `CoverageGroup`, `CoverageScope`, and `FunctionalCoverageSession` provide
   sampling namespaces and one simulation-wide lifecycle on top of
   `cocotb-coverage`.
3. Protocol packages can provide subscribers such as
   `altera.video.VIPPacketCoverage`.
4. An IP wrapper composes protocol subscribers with its parameter and semantic
   crosses, then adapts them to pyuvm ports through `AnalysisImp`.

The resulting flow is similar to a SystemVerilog UVM coverage subscriber: the
monitor publishes transactions, several independent subscribers consume them,
and the IP environment owns the connections. The coverpoint implementation is
from `cocotb-coverage`; the layering and lifecycle are supplied by
`fpga-verification`.

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
