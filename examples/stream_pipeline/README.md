<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Video-packet endianness example

This example verifies a one-entry Intel Avalon-ST Video pipeline that reverses
the byte order of each VIDEO payload beat. Packet identifier beats, CONTROL
packets and USER packets pass through unchanged. The final partial VIDEO beat
reverses only its valid bytes.

The testbench demonstrates the recommended `config`, `layout`, functional
model, behavior model, scoreboard, environment, test and runner boundaries.

From the `fpga-verification` repository root:

```bash
python -m pytest -q examples/stream_pipeline/tests
SIM=verilator python -m examples.stream_pipeline.simulation.vip.run_test
```

Use `SIM=questa` for a Questa run. Add `-g` after the module command to request
the simulator's debug mode.

The documentation site contains the complete
[tutorial](../../docs/tutorial/stream-pipeline.md).
