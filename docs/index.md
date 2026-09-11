<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# FPGA Verification

`fpga-verification` is a Python library for building repeatable FPGA tests from
the same set of data descriptions, protocol codecs, simulation components, and
hardware access helpers.

The library covers the path from a Python stimulus to a checked DUT response:

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

## Read this documentation in order

The chapters deliberately follow the way a verification environment grows:

1. [Architecture](guide/architecture.md) explains the library layers and the
   boundary between agents, behavior models, and scoreboards.
2. [Simulation runners](sim/runners.md) start a DUT in a supported simulator.
3. [Avalon-ST](guide/avalon-st.md) introduces transfers, frames, sources,
   sinks, and monitors.
4. [Intel video](guide/intel-video.md) adds packet meaning above the stream.
5. [VIP verification](guide/vip-verification.md) connects agents, models, and
   output expectations into a complete testbench.
6. [Performance](guide/performance.md) measures latency, bubbles, and sustained
   throughput after functional checking is in place.
7. [Control and memory](guide/control-and-memory.md) covers Avalon-MM and DMA
   traffic alongside the main stream.
8. [Hardware-in-the-loop](guide/hil.md) reuses Python-side data on a real FPGA.
9. [Video frames](guide/video-frames.md) and
   [numeric formats](guide/numeric-formats.md) document the lower-level data
   representations when a test needs them.

Each chapter links to an executable notebook with more examples. The notebooks
also state whether they need only Python, a cocotb simulator, Quartus tools, or
connected hardware.

## Project links

- [Package on PyPI](https://pypi.org/project/fpga-verification/)
- [Source repository](https://github.com/yarko18/fpga-verification)
- [Example notebooks](https://github.com/yarko18/fpga-verification/tree/main/examples)
