<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Simulation runners

The runner is the boundary between a human command line and a cocotb testbench.
Keep it small: select the DUT, source tree, test module and configuration here;
keep stimulus, expected data and bus setup in the testbench package.

All runners select `verilator` unless `SIM` is set. Use `SIM=questa` for an
interactive debug session or a generated design that requires Questa libraries.

```text
run_test.py -> runner -> compile / generate -> cocotb test module -> pyuvm Env
```

## Choose the entry point

| Entry point | Use it for |
| --- | --- |
| `run_rtl_test()` | Verilog/SystemVerilog sources, with optional prepared Intel libraries. |
| `run_component_test()` | An Altera component description that must be generated first. |

Both functions are imported from `fpga_verification.sim.runners`. They prepare
paths and logs, accept `-g`, and provide `--help` for runner options. Unknown
runner arguments produce an error with a `--help` hint. Calls made from pytest
continue to tolerate pytest's own command-line options. Compilation and
component-generation helpers are internal implementation details.

In a `run_test.py`, use the directory containing that file as `PROJECT_ROOT`:

```python
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
```

All relative source and component paths are resolved from this directory. Build
directories, generation output and logs consequently stay beside the test that
owns them.

The current API uses `sources` in both RTL and Intel component runners and
`load_test_config()` on the cocotb side. The former `source_dirs` and
`load_runtime_config()` names are not compatibility aliases; update callers
when moving to this version.

## Plain RTL

`run_rtl_test()` accepts `.v`/`.sv` files and directories together in
`sources`. Directories are scanned recursively. Relative paths are resolved
against `project_root`, absolute paths are used unchanged, and overlapping
entries are de-duplicated. When a directory is present, the resulting files are
ordered from their HDL dependencies rather than their filenames. An explicit
file-only list retains its declared order.

```python
import os
from pathlib import Path

from fpga_verification.sim.runners import run_rtl_test


def run_plain_rtl():
    os.environ["SIM"] = "verilator"
    run_rtl_test(
        project_root=Path(__file__).resolve().parent,
        hdl_toplevel="stream_component",
        test_module="stream.test_pyuvm",
        sources=("../../src/common", "../../src/stream_component.sv"),
        parameters={"DATA_WIDTH": 32},
    )
```

A typical source layout is intentionally boring:

```text
project/
  src/
    stream_component.sv
    common/
  simulation/
    stream/
      run_test.py
      test_pyuvm.py
      env.py
```

For example, a project can combine shared recursive trees with one package
file without manually maintaining their compilation order:

```python
run_rtl_test(
    project_root=PROJECT_ROOT,
    sources=(
        "../../rtl/common",
        "../../rtl/packet_processing",
        "../../rtl/packet_types_pkg.sv",
    ),
    hdl_toplevel="packet_processing",
    test_module="simulation.test",
)
```

### Quartus libraries without component generation

Plain RTL may instantiate Altera primitives directly. Give `run_rtl_test()`
simulator-independent library names and the runner compiles their models before
the project RTL:

```python
from fpga_verification.sim.runners import run_rtl_test


run_rtl_test(
    project_root=PROJECT_ROOT,
    sources=("../src",),
    hdl_toplevel="stream_fifo",
    test_module="simulation.test",
    parameter_presets=PARAMETER_PRESETS,
    intel_libraries=("altera_mf",),
)
```

The supported logical names are `lpm`, `altera_mf`, `altera_lnsim`, and
`altera_primitives`. For example, `lpm` resolves to `220model.v`, while
`altera_mf` resolves to `altera_mf.v`. The public configuration therefore does
not contain Questa- or Verilator-specific library names.

The model directory is resolved in this order:

1. the `quartus_sim_lib` argument;
2. `QUARTUS_SIM_LIB`;
3. `QUARTUS_ROOTDIR/eda/sim_lib`;
4. the Quartus installation containing `quartus_sh` or `ip-generate` on `PATH`.

Keep machine-specific installation paths in the environment. For an explicit
host-side selection, pass a local value such as
`quartus_sim_lib="/opt/intelFPGA/quartus/eda/sim_lib"` rather than committing a
developer's path to a reusable runner. Simulator compatibility fixes are
applied to copied models; installed Quartus files are never modified.

## Generated component

`run_component_test()` runs `ip-generate`, reads the generated `.spd` file,
joins generated composition HDL with source HDL, adds selected tool models,
then calls the internal RTL backend. The normal generated directory is
temporary.

Its `sources` argument has the same public name as the RTL runner argument, but
component generation uses it as a set of source-tree directories for IP
catalogue generation and matching generated HDL back to the original files.
For Verilator, the component runner adds `-Wno-PARAMNODEFAULT` automatically;
explicit `build_args` are reserved for design-specific options.

```python
from pathlib import Path

from fpga_verification.sim.runners import run_component_test


def run_generated_component(generate_only=False):
    return run_component_test(
        project_root=Path(__file__).resolve().parent,
        component_file=Path("../../src/component_hw.tcl"),
        sources=[Path("../../src/hw")],
        hdl_toplevel="component",
        test_module="stream.test_pyuvm",
        component_parameters={"DATA_WIDTH": 32},
        generate_only=generate_only,
    )
```

Use `generate_only=True` to retain and return the generated directory without
starting simulation. Use `retain_generated=True` after a normal run when a
failed generated tree needs investigation. Generated trees are build artifacts,
not source files: they depend on the selected tool version and simulator.

The generation flow is:

```text
sources
  -> ip-make-ipx --thorough-descent
  -> generated components catalogue
  -> ip-generate
  -> generated composition HDL + original source HDL
  -> internal RTL backend
```

Useful component options include `part`, `project_directory`,
`quartus_model_files`, `ip_search_paths` and `make_ipx`.

## One configuration for HDL and cocotb

For a plain or generated DUT, use one resolved `ComponentConfig`. Fields marked
with `hdl_parameter()` are passed to RTL compilation or component generation;
the same resolved object is serialised into the cocotb environment. The
testbench restores it with `load_test_config()`.

```python
from dataclasses import dataclass

from fpga_verification.sim import ComponentConfig, hdl_parameter


@dataclass(frozen=True)
class TestConfig(ComponentConfig):
    data_width: int = hdl_parameter(32, name="DATA_WIDTH")
    queue_depth: int = hdl_parameter(8, name="QUEUE_DEPTH")
    case_note: str = "smoke"
```

```python
# Host side, in run_test.py
run_rtl_test(..., config=TestConfig())
run_component_test(..., config=TestConfig())

# Cocotb side, in test_pyuvm.py
cfg = load_test_config(TestConfig)
```

Do not also pass a conflicting `component_parameters` mapping. A missing,
stale or malformed runtime configuration is an error by design: creating a
new default config in cocotb would hide a mismatch with generated HDL. See
[Project style](../guide/testbench-style.md) for the ownership rule.

Put reusable single-run configurations in a preset mapping:

```python
PARAMETER_PRESETS = {
    "default": TestConfig,
    "wide": lambda: TestConfig(data_width=64),
}
```

Pass the mapping to `parameter_presets=` instead of `config=`. A mapping must
contain `default`; its values may be ready configurations or zero-argument
factories. The runner evaluates only the selected factory.

An ordinary run uses `default`. Select another preset explicitly:

```bash
python run_test.py --param-preset wide
```

The runner names an explicitly selected preset and prints its resolved fields.
Fields passed to HDL are identified in a separate column:

```text
Selected parameter preset: wide
╭────────────────┬─────────┬─────────────────╮
│ Config field   │ Value   │ HDL parameter   │
├────────────────┼─────────┼─────────────────┤
│ data_width     │ 64      │ DATA_WIDTH      │
│ queue_depth    │ 8       │ QUEUE_DEPTH     │
│ case_note      │ "smoke" │ —               │
╰────────────────┴─────────┴─────────────────╯
```

Parameter presets are only for ordinary single-configuration runs.
`--param-preset` together with `--matrix` is an error. Use repeatable
`--matrix --test PATTERN` options to select particular cocotb or pyuvm tests
without changing the matrix baseline.

When the same tests must cover several elaborated parameter sets, use the
[parameter matrix guide](../guide/parameter-matrix.md). Matrix domains are
optional metadata, relevance is declared beside each cocotb/pyuvm test, and
illegal `TestConfig` combinations are removed before a simulator starts.

## A human-readable `run_test.py`

A command-line runner should be readable without opening the environment. It
may contain documented simulator workarounds; it must not calculate expected
results or construct agents.

```python
from pathlib import Path

from fpga_verification.sim.runners import run_component_test

from .config import PARAMETER_PRESETS


if __name__ == "__main__":
    run_component_test(
        project_root=Path(__file__).resolve().parent,
        component_file="../../src/component_hw.tcl",
        hdl_toplevel="component",
        test_module="stream.test_pyuvm",
        parameter_presets=PARAMETER_PRESETS,
        enable_questa_acc=True,
    )
```

Run it with:

```bash
SIM=verilator python -m simulation.stream.run_test
SIM=questa python -m simulation.stream.run_test -g
SIM=verilator python -m simulation.stream.run_test --test 'Video*'
```

## Debugging

`-g` enables debug mode in both script wrappers.

| Simulator | Debug result |
| --- | --- |
| Verilator | Enables tracing and creates `dump.vcd`; there is no GUI. |
| Questa | Starts the GUI, enables signal access, writes waves and runs `wave.do` when present. |

For Questa without the GUI, set `QUESTA_ACC=1` to retain signal visibility.
Compile and IP-generation output is written under the test's `logs/` directory.
