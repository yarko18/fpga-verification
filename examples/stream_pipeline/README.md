<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Stream pipeline

`rtl/stream_pipeline.sv` reverses valid bytes in each Avalon-ST VIDEO payload
beat. `USE_FIFO` selects its storage implementation.

## test_1: plain RTL

Runs with `USE_FIFO=False` and does not load vendor libraries.

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.test_1.run_test
```

## test_2: Altera FIFO

Uses the same RTL with its own testbench, `USE_FIFO=True` and `altera_mf`.

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.test_2.run_test
```

Use `SIM=questa` for Questa and `-g` for debug mode. Set `QUARTUS_SIM_LIB` when
the Quartus simulation library is not discovered automatically.
