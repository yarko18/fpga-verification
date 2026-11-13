<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Installation

`fpga-verification` supports Python 3.10 through 3.13.

## Install a release

```bash
python -m pip install fpga-verification
```

The package installs the neutral data helpers, cocotb and pyuvm components,
simulation runners, and hardware-in-the-loop utilities together.

## Develop the library

From a repository checkout:

```bash
python -m pip install -e ".[docs]"
python -m pytest -q
./docs/mkdoc.sh build
```

The documentation command builds the site with MkDocs strict mode. Set
`FPGA_DOCS_PYTHON` when `python3.12` is not the desired interpreter:

```bash
FPGA_DOCS_PYTHON=python3 ./docs/mkdoc.sh build
```

## Requirements

### Normal installation

| Requirement | Used for |
| --- | --- |
| Python 3.10--3.13 and `pip` | All installations |
| `verilator`, `perl`, `make`, and a C++20 compiler in `PATH` | Verilator simulations (the default) |
| `vsim`, `vlog`, and `vlib` in `PATH` | Questa simulations |
| `vcom` in `PATH` | Questa simulations containing VHDL |

`pip` installs all Python runtime dependencies declared in `pyproject.toml`:
NumPy, cocotb, cocotbext-avalon, pyuvm, pytest, tqdm, and VUnit. No additional
Python packages are required for normal use.

Verilator needs no fpga-verification environment variables. To select Questa,
set `SIM=questa`. Simulator licence variables, when required, are specific to
the local Questa installation.

### Optional Intel/Altera tools

Quartus is not required for pure RTL without Intel primitives.

| Feature | Requirement |
| --- | --- |
| Compile Intel simulation models | Locate Quartus `eda/sim_lib` using the runner's `quartus_sim_lib` argument, `QUARTUS_SIM_LIB`, `QUARTUS_ROOTDIR`, or `quartus_sh`/`ip-generate` in `PATH` |
| Generate an Intel component | `ip-generate` and, when an IP index is built, `ip-make-ipx` in `PATH` |
| Use hardware-in-the-loop helpers | `system-console` in `PATH` |

`QUARTUS_SIM_LIB` must point directly to `eda/sim_lib`.
`QUARTUS_ROOTDIR` must point to the Quartus installation root. These variables
locate simulation models; generated component simulations still require the
executables in `PATH`.

### Development-only tools

| Task | Additional requirements |
| --- | --- |
| Build documentation | `pip install -e ".[docs]"`; `drawio` in `PATH` for Draw.io diagrams; `xvfb-run` on headless Linux |
| Use `docs/mkdoc.sh` | Bash; `FPGA_DOCS_PYTHON` is optional and overrides its default Python command |
| Build a binary wheel manually | `build`, setuptools, wheel, Cython, and a native C/C++ compiler |
| Use `tools/build_binary_wheel.ps1` | PowerShell; the script sets `FPGA_VERIFICATION_BINARY` itself |

Bash and PowerShell are helper-script requirements, not package runtime
requirements. Windows `taskkill`, used to stop matrix workers, is part of
Windows and requires no separate installation.
