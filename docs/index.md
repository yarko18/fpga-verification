<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# FPGA Verification

`fpga-verification` is a Python library for repeatable FPGA verification. It
keeps test data, protocol conversion, reference behaviour and simulation
plumbing in separate layers, so the same prediction code can be used in a fast
unit test, cocotb and hardware-in-the-loop.

```text
test data -> protocol codec -> driver -> DUT -> monitor -> scoreboard
                                                        -> performance metrics

test data <---------------- Intel System Console ----------------> FPGA board
```

It includes:

- cocotb helpers for Avalon-ST and Avalon-MM interfaces;
- Intel Avalon-ST Video packet codecs and pyuvm verification components;
- simulation runners for plain RTL, Intel components, and Platform Designer;
- a black-box Intel DMA model and sparse byte memory;
- stream latency and throughput measurements;
- simulator-independent video and numeric data helpers;
- persistent Intel System Console access for hardware-in-the-loop tests.

## Install

`fpga-verification` supports Python 3.10 through 3.13. Install the released
package from PyPI:

```bash
python -m pip install fpga-verification
```

For development of the library itself:

```bash
git clone https://github.com/yarko18/fpga-verification.git
cd fpga-verification
python -m pip install -e ".[docs]"
```

## Documentation path

For a new testbench, read these chapters in order:

1. [Architecture](guide/architecture.md) gives the responsibility boundaries.
2. [Project style](guide/testbench-style.md) defines the files in
   `simulation/<name>/` and their ownership rules.
3. [Simulation runners](sim/runners.md) starts plain RTL, generated
   components, or a Platform Designer system.
4. [Modelling DUT behaviour](guide/modeling.md) creates the pure functional
   model, stateful behaviour model and protocol adapter.
5. [Verification environment](guide/vip-verification.md) connects agents and
   scoreboards, drives tests and finishes cleanly.

Read the interface chapters as they become relevant: [Avalon-ST](guide/avalon-st.md),
[Avalon-MM and DMA](guide/control-and-memory.md), and
[Intel Avalon-ST Video](guide/intel-video.md). The data chapters describe
[video frames](guide/video-frames.md) and [numeric formats](guide/numeric-formats.md).

The site contains the material formerly kept in `examples/`. It is therefore
self-contained; notebooks are not needed to read or use the documentation.

## Project links

- [Package on PyPI](https://pypi.org/project/fpga-verification/)
- [Source repository](https://github.com/yarko18/fpga-verification)
