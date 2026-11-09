<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Stream pipeline

`rtl/stream_pipeline.sv` reverses valid bytes in each Avalon-ST VIDEO payload
beat. `USE_FIFO` selects its storage implementation.

## test_1: plain RTL

Runs with `USE_FIFO=False` and use pure RTL sources.

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.test_1.run_test
```

## test_2: Altera FIFO

Same test with RTL sources but with included FIFO. FIFO IP is provided by vendor
so we need to use `altera_mf` library to support `USE_FIFO=True` parameter.

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.test_2.run_test
```

`test_2` also demonstrates named host configurations. For example:

```bash
FPGA_VERIFICATION_CONFIG_CASE=preset2 \
SIM=verilator python -m examples.stream_pipeline.simulation.test_2.run_test
```

Each runner treats its own directory as `PROJECT_ROOT`. Consequently its
`sim_build_<simulator>/` and `logs/` directories are created under
`simulation/test_1/` or `simulation/test_2/`, not at the example root.

Use `SIM=questa` for Questa and `-g` for debug mode. Set `QUARTUS_SIM_LIB` when
the Quartus simulation library is not discovered automatically.
