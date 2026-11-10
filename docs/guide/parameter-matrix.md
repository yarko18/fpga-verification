<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Parameter matrix simulations

A parameter matrix runs the same cocotb or pyuvm tests against several HDL
elaborations. It is useful when a component supports widths, channel counts,
algorithms or operating directions that are fixed at build time.

An HDL parameter is not a runtime input. Every unique configuration requires a
separate component generation and simulator build. The matrix runner therefore
plans configurations before starting a simulator, removes illegal candidates,
and groups tests that can share one build.

The ordinary single-configuration workflow remains the starting point. Add a
matrix after the DUT model and tests work for one configuration; matrix metadata
is optional and does not change a normal run.

The first implementation is integrated with the Intel component
`run_component_test()` wrapper. The planning model is vendor-independent, but
plain RTL and pre-generated Platform Designer entry points do not yet expose
the matrix command-line mode.

## Single and matrix runs

Keep the existing command for one resolved configuration:

```bash
python run_test.py
```

Request the declarations attached to the test module with:

```bash
python run_test.py --matrix
```

Before committing to a large number of HDL builds, inspect the plan:

```bash
python run_test.py --matrix --plan
```

The planner reports candidate runs, legal runs, runs selected by each test's
strategy, unique configurations after grouping, and the number of discovered
test cases. Planning imports Python test modules and constructs configuration
objects; it does not invoke component generation or a simulator.

Use a glob to select one or more simulator tests before planning:

```bash
python run_test.py --matrix --test 'Video*'
```

## Describe independent parameters

`ComponentConfig` remains the single resolved contract shared by HDL generation
and the testbench. A field marked with `hdl_parameter()` is passed to HDL and is
also present in the JSON configuration loaded by cocotb.

Add `values` only when matrix work begins:

```python
from dataclasses import dataclass

from fpga_verification.sim import ComponentConfig, hdl_parameter


@dataclass(frozen=True)
class TestConfig(ComponentConfig):
    operation: str = hdl_parameter(
        "UNPACK",
        name="OPERATION",
        values=("PACK", "UNPACK", "PAD", "UNPAD"),
    )
    native_bits_per_symbol: int = hdl_parameter(
        16,
        name="NATIVE_BITS_PER_SYMBOL",
        values=range(4, 33),
    )
    native_color_planes: int = hdl_parameter(
        1,
        name="NATIVE_COLOR_PLANES",
        values=range(1, 5),
    )
    uniform_bits_per_symbol: int = hdl_parameter(
        16,
        name="UNIFORM_BITS_PER_SYMBOL",
        values=range(4, 33),
    )
```

`values` is deliberately optional. A developer can write and debug ordinary
tests without defining a parameter domain. The planner requires a domain only
when a test lists that field in `vary`.

Use `matrix_parameter()` for an independent configuration choice needed by the
test and build setup but not passed directly to HDL:

```python
operation: str = matrix_parameter(
    "PACK",
    values=("PACK", "UNPACK", "PAD", "UNPAD"),
)
```

Like any runtime config field, it is included in the JSON loaded by the test.
Unlike `hdl_parameter()`, it is absent from `to_parameters()`.

## Do not put derived HDL parameters in `TestConfig`

Configuration fields describe independent public choices. Do not add `MODE`,
`DIRECTION`, `FACTOR`, bus widths or similar values when they can be calculated
from other fields. Duplicating a derived value creates contradictory states and
turns invalid combinations into matrix dimensions.

If the top-level component calculates those values internally, no runner code
is needed. If a lower-level component exposes them as HDL parameters, calculate
them at the runner boundary:

```python
def derived_component_parameters(cfg):
    native_width = cfg.native_bits_per_symbol * cfg.native_color_planes
    return {
        "MODE": "PACK" if cfg.operation in {"PACK", "UNPACK"} else "PAD",
        "DIRECTION": (
            "NativeUniform"
            if cfg.operation in {"PACK", "PAD"}
            else "UniformNative"
        ),
        "FACTOR": (
            cfg.uniform_bits_per_symbol // native_width
            if cfg.operation in {"PACK", "UNPACK"}
            else 1
        ),
    }


run_component_test(
    ...,
    config=TestConfig(),
    derived_parameters=derived_component_parameters,
)
```

The callback receives the final matrix configuration, not the baseline object
created by `run_test.py`. Derived names may not override independent HDL
parameters.

## Define legality in `__post_init__`

One parameter domain usually contains values that are individually valid but
illegal together. Keep those rules with the configuration:

```python
def __post_init__(self):
    native_width = self.native_bits_per_symbol * self.native_color_planes

    if native_width > self.uniform_bits_per_symbol:
        raise ValueError("native pixel must fit inside one uniform beat")

    if self.operation in {"PACK", "UNPACK"}:
        if self.uniform_bits_per_symbol % native_width:
            raise ValueError("PACK/UNPACK require an integer factor")
        if self.uniform_bits_per_symbol // native_width not in {1, 2, 4}:
            raise ValueError("factor must be 1, 2, or 4")
```

The planner constructs every candidate needed by a strategy. A `ValueError`
raised by `__post_init__` marks that candidate as illegal and removes it before
execution. It is not a skipped or failed simulation. Other exceptions indicate
a programming error and stop planning.

This is the same validation used when loading the resolved JSON in cocotb, so
host generation and testbench behavior cannot silently disagree.

## Declare relevance next to each test

The test author knows which HDL parameters affect a behavior. Record that fact
beside the test rather than creating a global list of named cases.

For pyuvm:

```python
from fpga_verification.sim import balance, parameter_matrix


@parameter_matrix(
    vary=(
        "operation",
        "native_bits_per_symbol",
        "native_color_planes",
        "uniform_bits_per_symbol",
    ),
    strategy=balance(),
)
@pyuvm.test()
class VideoPacketTest(SymbolAdapterVIPTest):
    ...
```

For a direct cocotb test the order is the same:

```python
@parameter_matrix(
    vary=("input_width", "output_width"),
    strategy=balance(),
)
@cocotb.test()
async def test_conversion(dut):
    ...
```

Fields omitted from `vary` keep their baseline values. A test without
`@parameter_matrix` runs once at the baseline during a matrix invocation. The
decorator is inert during `python run_test.py`.

## Choose an explicit strategy

The strategy is required whenever `vary` is non-empty. This prevents a new
range from accidentally turning a small test into thousands of builds.

`exhaustive()` selects every legal combination. It is the only strategy that
means “all combinations.”

`balance()` selects a compact legal set in which every reachable individual
value appears at least once. The baseline is included when it is legal. When
several candidates add the same number of uncovered values, the planner
prefers values that have occurred less often. This keeps small categorical
domains from collapsing onto their first value while preserving a compact
cover. It does not promise pairwise or higher-order interaction coverage.

`random_subset(count=N, seed=S)` selects at most `N` legal configurations.
The explicit seed makes the sample reproducible and is stored in
`logs/matrix-results.json`. Random selection provides no value or interaction
coverage guarantee, so use it as a bounded supplement rather than as a
replacement for `balance()`.

Always run `--plan` after changing domains, legality rules or strategy. There is
no silent maximum and no automatic downgrade from exhaustive to another rule.

## Builds are grouped, not duplicated

The planner first expands each test independently. It then hashes the complete
resolved `TestConfig` and combines tests requesting the same configuration:

```text
configuration 7bc421a9
  ControlPacketTest
  UserPacketTest
  VideoPacketTest
```

That configuration is generated and compiled once. Cocotb filters the
simulation to the listed tests. The plan therefore reports both unique
`configs` and total `runs`; these counts answer different questions. A test
case is one discovered cocotb or pyuvm test. A run is one test case assigned to
one configuration.

## Progress, results and logs

Matrix output stays compact:

```text
[configs 17/35 | runs 49/101] 7bc421a9 PASS  3/3 runs 8.41s
```

Successful rows show only a stable short configuration ID. Full parameter lists
would make a large-IP run unreadable.

At the end, one table aggregates pass, fail, error and skip counts by test. Full
parameter values and the saved log path are printed only for failed
configurations.

Each job writes into a disposable `.matrix_work/<config-id>` directory.
Successful logs and builds are removed. A failed job is moved to
`logs/matrix_failures/<config-id>` with its simulator build and
`simulation.log`. The small `logs/matrix-results.json` manifest is always
retained; it contains resolved configurations, strategies, test results and
timings and can later feed parameter coverage reporting.

Pytest is an internal job orchestrator. It supplies isolation, result handling
and a standard process exit status, but project tests do not need a separate
pytest file and the public command remains `python run_test.py --matrix`.

Parameter coverage and coverage-driven selection are intentionally separate
future features. A matrix strategy states what was scheduled now; it must not
be presented as stronger coverage than it actually provides.
