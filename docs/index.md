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

## Start here

1. [Install the package](getting-started/install.md).
2. [Run the minimal testbench](getting-started/minimal-testbench.md).
3. Follow the complete [generic stream-pipeline tutorial](tutorial/stream-pipeline.md).

The tutorial answers how to assemble a working testbench. The
[architecture](guide/architecture.md) and [modeling](guide/modeling.md) chapters
explain why the responsibilities are separated. Focused how-to guides cover
runners, interfaces, data formats, performance and hardware access.

The case studies describe reusable verification problems:

- a [stateless stream converter](case-studies/stateless-converter.md);
- a [stateful frame transform](case-studies/stateful-transform.md);
- a [memory-backed streaming component](case-studies/memory-backed-component.md).

Use the generated [API reference](reference/simulation.md) when you already know
which component you need.

## Project links

- [Package on PyPI](https://pypi.org/project/fpga-verification/)
- [Source repository](https://github.com/yarko18/fpga-verification)
