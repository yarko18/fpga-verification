<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Endianity swap

This example verifies a plain RTL Avalon-ST block with library BFMs and a
Python reference model. USER packets pass through unchanged; valid symbols in
each VIDEO payload beat are reversed. It also demonstrates typed HDL/test
configuration and parameter-matrix tests without pyuvm or component Tcl.

```bash
cd examples/endianity_swap/simulation
SIM=verilator python run_test.py
```

Select one test or a named single-run parameter preset:

```bash
SIM=verilator python run_test.py --test test_video_packet
SIM=verilator python run_test.py --param-preset custom1
```

Inspect or execute the declared matrix with:

```bash
SIM=verilator python run_test.py --matrix --plan
SIM=verilator python run_test.py --matrix
```

Use `SIM=questa` for Questa and `-g` for debug mode.
