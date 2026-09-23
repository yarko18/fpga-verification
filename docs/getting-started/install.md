<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
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

## Simulator requirements

Plain RTL tests require a cocotb-supported simulator. The project runners use
Verilator by default and use Questa when `SIM=questa` is set. Generated Intel
components additionally require the matching Quartus command-line tools.

The Python-only video, numeric-format, packet-codec, and model tests do not
require a simulator.
