<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5

Unless explicitly acquired and licensed from Licensor under another license,
the contents of this file are subject to the Reciprocal Public License ("RPL")
Version 1.5, or subsequent versions as allowed by the RPL, and You may not copy
or use this file in either source code or executable form, except in compliance
with the terms and conditions of the RPL.

All software distributed under the RPL is provided strictly on an "AS IS"
basis, WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, AND LICENSOR
HEREBY DISCLAIMS ALL SUCH WARRANTIES, INCLUDING WITHOUT LIMITATION, ANY
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, QUIET
ENJOYMENT, OR NON-INFRINGEMENT. See the RPL for specific language governing
rights and limitations under the RPL.
-->

# Simulation Runners

You can run Cocotb test using Makefile or with python runner. Python runner method is used in this project.


## Runners

The simulation helpers cover three levels of generated and non-generated
designs:

1) Low-level runners (library/pytest):
 - `rtl_test_cocotb`

    RTL sources -> cocotb build/test

 - `intel_component_test_cocotb`

    *_hw.tcl -> ip-generate -> generated composition HDL + original RTL -> rtl_runner

2) Script wrappers (shared CLI setup):
 - `run_rtl_test`

    Run a standard RTL cocotb simulation from a script or pytest.

 - `run_intel_component_test`

    Run a standard Intel component cocotb simulation from a small script or pytest.

### RTL sources

`rtl_test_cocotb` is the direct RTL path. Pass it explicit HDL sources or source
directories, and it delegates build/test to the selected cocotb simulator runner.

#### Example for run_rtl_test:

```verilog
  from pathlib import Path

  from fpga_verification.sim.runners import run_rtl_test


  if __name__ == "__main__":
      project_root = Path(__file__).resolve().parent

      run_rtl_test(
          project_root=project_root,
          hdl_toplevel="MyIP",
          test_module="vip.test_pyuvm",
          test_module_env="MYIP_VIP_TEST_MODULE",
          source_dirs=("src",),
          enable_questa_acc=True,
      )
```

where project stucture looks like:
```
project/
  ├── run_test.py
  ├── src/
  │   ├── MyIP.sv
  │   └── other_module.sv
  └── vip/
      └── test_pyuvm.py
```


### Intel component runner

`intel_component_test_cocotb` is for Platform Designer component `_hw.tcl` files.
It generates only the HDL needed for simulation, keeps composition HDL that has
no source equivalent, replaces generated copies of project RTL with exact
matches from `source_dirs`, and then calls `rtl_test_cocotb`.

Its generated-catalog flow is:

```text
source_dirs
  -> ip-make-ipx --thorough-descent --source-directory=<source_dirs>
  -> components.ipx in generated temp dir
  -> ip-generate --search-path=<components.ipx>,$
  -> parse .spd
  -> replace generated RTL copies with original source files
  -> rtl_test_cocotb
```

Pass `generate_only=True` to retain and return the generated composition
directory without running simulation.


#### Example for run_intel_component_test:

```verilog
from pathlib import Path

from fpga_verification.sim.runners import run_intel_component_test

from test_config import get_test_config

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent

    run_intel_component_test(
        project_root=project_root,
        component_file="./src/MyIP_hw.tcl",
        hdl_toplevel="MyIP_component",
        test_module="vip.test_pyuvm",
        test_module_env="MYIP_VIP_TEST_MODULE",
        config=get_test_config(),
        enable_questa_acc=True,
        build_args=build_args,
    )
```

where project stucture looks like:
```
project/
  ├── run_test.py
  ├── src/
  │   ├── MyIP.sv
  │   └── MyIP_hw.tcl
  └── vip/
      └── test_pyuvm.py
```

### Resolved component configuration

Define generated-component configuration as a dataclass inheriting
`ComponentConfig`, and mark Platform Designer values with `hdl_parameter()`.
`run_intel_component_test()` uses `to_parameters()` to generate the DUT and
passes the same resolved object as JSON to cocotb through
`Runner.test(extra_env=...)`.
Providing a conflicting `component_parameters` mapping together with `config`
is rejected before generation.

```python
@dataclass(frozen=True)
class TestConfig(ComponentConfig):
    width: int = hdl_parameter(32, name="MAX_WIDTH")
    case_note: str = "smoke"


config = get_test_config(os.getenv("FPGA_VERIFICATION_CONFIG_CASE", "smoke"))
run_intel_component_test(..., config=config)
```

The cocotb module must restore it with `load_runtime_config(TestConfig)`.
Missing JSON, malformed JSON, missing/extra fields, and wrong JSON field types
are errors; constructing `TestConfig()` inside cocotb is intentionally not a
fallback. Named cases therefore select host-side configurations only, while
`FPGA_VERIFICATION_TEST_CONFIG_JSON` remains the sole configuration seen by the
running testbench.

## Simulator setup

All runners use Verilator by default. Set the `SIM` environment variable to select simulator explicitly.

run_test.py:
```python
os.environ["SIM"] = "questa"

run_rtl_test(
    # ...
)
run_intel_component_test(
    # ...
)
```

or directly in CLI:

```bash
        # use Questa
        SIM=questa python run_test.py

        # use Verilator
        SIM=verilator python run_test.py
```


For Questa, the platform runner compiles through `msim_setup.tcl` and runs
cocotb against the generated simulator libraries. For Verilator, it reads
Verilog/SystemVerilog sources from `msim_setup.tcl` and builds them directly.

```text
project_root/
  <hdl_toplevel>/
    <hdl_toplevel>/
      testbench/
        mentor/
          msim_setup.tcl
```

## Debug mode

Both script wrappers accept the `-g` flag to enable debug mode:

        python run_test.py -g

Behavioral for different simulators:
- Verilator:
  - still no GUI
  - enable `VM_TRACE=1`
  - add `--trace` flag during compilation  phase
  - add `--trace` flag during run phase
  - create `dump.vcd` file

- Questa:
  - run GUI
  - enable access to all signals using `+acc`
  - enable waveform write
  - run `wave.do` script (if avaliable) to open already configured waveform


For a plain RTL run script:

```python
from pathlib import Path

from fpga_verification.sim.runners import run_rtl_test


if __name__ == "__main__":
    run_rtl_test(
        project_root=Path(__file__).parent,
        hdl_toplevel="dut",
        test_module="test_dut",
    )
```

For pytest or another Python caller, either call the low-level runner and pass
`debug` explicitly, or call a script wrapper. Script wrappers ignore pytest's
own command-line arguments:

```python
def test_rtl():
    run_rtl_test(
        project_root=Path(__file__).parent,
        hdl_toplevel="dut",
        test_module="test_dut",
        debug=True,
    )
```
