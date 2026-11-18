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

Without the flag, the optional library is not imported and the same cocotb
tests run only their correctness checks.

## Where coverage belongs

Do not put DUT-specific bins in a generic BFM or protocol agent. A BFM owns bus
timing and a monitor owns accepted transactions; neither knows which values or
crosses are important for a particular IP.

For a structured pyuvm testbench, keep the coverage model beside the
testbench, normally in `simulation/<name>/coverage.py`. Instantiate a coverage
collector in the environment and connect it to the same monitor analysis port
used by scoreboards and metrics:

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

## Scope of the current integration

`fpga-verification` passes the `--coverage` mode into individual cocotb and
pyuvm testbenches and provides common reset/report helpers. Coverage is
intentionally an optional dependency, so users that only need runners and BFMs
do not pay for it.

Coverage artifacts are not yet first-class matrix-run outputs, so
`--coverage` and `--matrix` are currently mutually exclusive. Each matrix job
runs in an isolated process and successful temporary directories are removed;
a production matrix integration therefore needs stable per-configuration
coverage paths, merging after all workers finish, and an explicit threshold
policy. Until that is added, export coverage from ordinary runs or preserve and
merge explicitly named files outside disposable matrix work directories.

See the
[registered-adder demo](https://github.com/yarko18/fpga-verification/tree/main/examples/adder_coverage)
for a complete small run that reaches and checks a declared coverage target.
