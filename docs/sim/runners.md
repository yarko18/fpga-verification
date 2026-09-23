<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
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
| `rtl_test_cocotb()` | Plain Verilog or SystemVerilog sources. |
| `intel_component_test_cocotb()` | A component description that must be generated first. |
| `platform_test_cocotb()` | An already generated Platform Designer simulation tree. |
| `run_rtl_test()` | A concise command-line wrapper around the RTL runner. |
| `run_intel_component_test()` | A concise command-line wrapper around the component runner. |

Low-level functions are useful from pytest or a Python tool. `run_*` wrappers
are normally the right choice for `simulation/<name>/run_test.py`: they prepare
paths and logs, accept `-g`, and ignore unrelated pytest options.

## Plain RTL

`rtl_test_cocotb()` either receives explicit `sources` or recursively discovers
`.v` and `.sv` files in `source_dirs`. It creates `sim_build_<SIM>`, forwards
HDL parameters, runs the cocotb module, and treats a failed results XML as a
failed Python process.

```python
import os
from pathlib import Path

from fpga_verification.sim.runners import rtl_test_cocotb


def run_plain_rtl():
    os.environ["SIM"] = "verilator"
    rtl_test_cocotb(
        project_root=Path("."),
        hdl_toplevel="stream_component",
        test_module="stream.test_pyuvm",
        sources=[Path("src/stream_component.sv")],
        parameters={"DATA_WIDTH": 32},
        compile_log=Path("logs/verilator_compile.log"),
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

Use explicit sources when source order matters. Otherwise pass source
directories and let the runner discover HDL files.

## Generated component

`intel_component_test_cocotb()` runs `ip-generate`, reads the generated `.spd`
file, joins generated composition HDL with source HDL, adds selected tool
models, then calls the RTL runner. The normal generated directory is temporary.

```python
from pathlib import Path

from fpga_verification.sim.runners import intel_component_test_cocotb


def run_generated_component(generate_only=False):
    return intel_component_test_cocotb(
        project_root=Path("."),
        component_file=Path("src/component_hw.tcl"),
        source_dirs=[Path("src/hw")],
        hdl_toplevel="component",
        test_module="stream.test_pyuvm",
        component_parameters={"DATA_WIDTH": 32},
        build_args=["-Wno-PARAMNODEFAULT"],
        generate_only=generate_only,
        ip_generate_log=Path("logs/ip_generate.log"),
        compile_log=Path("logs/verilator_compile.log"),
    )
```

Use `generate_only=True` to retain and return the generated directory without
starting simulation. Use `retain_generated=True` after a normal run when a
failed generated tree needs investigation. Generated trees are build artifacts,
not source files: they depend on the selected tool version and simulator.

The generation flow is:

```text
source_dirs
  -> ip-make-ipx --thorough-descent
  -> generated components catalogue
  -> ip-generate
  -> generated composition HDL + original source HDL
  -> rtl_test_cocotb
```

Useful component options include `part`, `project_directory`,
`quartus_model_files`, `ip_search_paths` and `make_ipx`.

## One configuration for HDL and cocotb

For a generated DUT, use one resolved `ComponentConfig`. Fields marked with
`hdl_parameter()` are passed to generation; the same resolved object is
serialised into the cocotb environment. The testbench restores it with
`load_runtime_config()`.

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
run_intel_component_test(..., config=get_test_config())

# Cocotb side, in test_pyuvm.py
cfg = load_runtime_config(TestConfig)
```

Do not also pass a conflicting `component_parameters` mapping. A missing,
stale or malformed runtime configuration is an error by design: creating a
new default config in cocotb would hide a mismatch with generated HDL. See
[Project style](../guide/testbench-style.md) for the ownership rule.

## Platform Designer system

`platform_test_cocotb()` targets an existing generated simulation tree.
With Questa it compiles through `msim_setup.tcl` and uses the generated
libraries. With Verilator it extracts a compatible source list from that setup.
Other simulator values are rejected.

```python
from fpga_verification.sim.platform_designer import platform_test_cocotb


platform_test_cocotb(
    project_root="platforms/system/sim",
    hdl_toplevel="system",
    test_module="system.test_pyuvm",
    debug=False,
)
```

Keep the project root, top-level name, selected simulator and installed tool
version consistent with the generated tree.

## A human-readable `run_test.py`

A command-line runner should be readable without opening the environment. It
may contain documented simulator workarounds; it must not calculate expected
results or construct agents.

```python
import os
from pathlib import Path

from fpga_verification.sim.runners import run_intel_component_test

from .config import get_test_config


if __name__ == "__main__":
    sim = os.getenv("SIM", "verilator")
    build_args = ["-Wno-PARAMNODEFAULT"] if sim == "verilator" else []

    run_intel_component_test(
        project_root=Path(__file__).resolve().parent,
        component_file="../../src/component_hw.tcl",
        hdl_toplevel="component",
        test_module="stream.test_pyuvm",
        config=get_test_config(),
        enable_questa_acc=True,
        build_args=build_args,
    )
```

Run it with:

```bash
SIM=verilator python -m simulation.stream.run_test
SIM=questa python -m simulation.stream.run_test -g
```

## Debugging

`-g` enables debug mode in both script wrappers.

| Simulator | Debug result |
| --- | --- |
| Verilator | Enables tracing and creates `dump.vcd`; there is no GUI. |
| Questa | Starts the GUI, enables signal access, writes waves and runs `wave.do` when present. |

For Questa without the GUI, set `QUESTA_ACC=1` to retain signal visibility.
`compile_log` and `ip_generate_log` keep tool output outside the source tree.

Next: [connect an Avalon-ST stream](../guide/avalon-st.md).
