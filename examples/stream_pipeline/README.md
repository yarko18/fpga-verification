<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Stream pipeline

Both RTL implementations reverse the valid bytes of each Avalon-ST VIDEO
payload beat and use the same cocotb test:

- `rtl/stream_pipeline.sv` — register stage;
- `rtl/stream_pipeline_fifo.sv` — Intel `scfifo`.

From the `fpga-verification` repository root:

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.vip.run_test
SIM=verilator python -m examples.stream_pipeline.simulation.vip.run_test_fifo
```

Or directly from `examples/stream_pipeline`:

```bash
SIM=verilator python simulation/vip/run_test.py
SIM=verilator python simulation/vip/run_test_fifo.py
```

Use `SIM=questa` for Questa and `-g` for debug mode. The FIFO runner loads
`altera_mf`; set `QUARTUS_SIM_LIB` if the Quartus simulation library is not
discovered automatically.
