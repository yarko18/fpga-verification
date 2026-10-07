<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Video-packet pipeline with an Intel FIFO

This example has the same observable contract and reuses the same verification
environment as [`stream_pipeline`](../stream_pipeline). Its RTL stores converted
beats in an Intel `scfifo`, so the plain RTL runner is configured with the
simulator-independent `altera_mf` library name. No Platform Designer component
or `_hw.tcl` file is involved.

From the `fpga-verification` repository root:

```bash
SIM=verilator python -m examples.stream_pipeline_fifo.simulation.vip.run_test
```

Use `SIM=questa` for Questa. The runner finds `eda/sim_lib` through
`QUARTUS_SIM_LIB`, `QUARTUS_ROOTDIR`, or Quartus executables on `PATH`. An
installation can also be selected explicitly with the `quartus_sim_lib`
argument; machine-specific installation paths should stay outside source
control.
