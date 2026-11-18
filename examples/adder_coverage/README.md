<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Registered adder functional coverage

The example has one runner and two ordinary cocotb tests: readable manual
examples and reproducible random additions. The random test declares coverage
for all four operand-sign combinations: `++`, `+-`, `-+`, and `--`.

An ordinary run needs only the default project dependencies:

```bash
cd examples/adder_coverage/simulation
python run_test.py
```

For a coverage run, install the optional dependency and use the same runner
with Python 3.11 or newer:

```bash
python -m pip install -e ".[functional-coverage]"
cd examples/adder_coverage/simulation
python run_test.py --coverage
```

`simulation/config.py` keeps the HDL width, matrix domain, random seed/count,
and required coverage percentage together. `--matrix` runs the random test for
the declared `DATA_WIDTH` values. Coverage and matrix modes are currently
separate because matrix coverage artifacts are not merged yet.

The coverage run prints every bin and writes `simulation/adder_coverage.xml`.
Its 100% target means that all four sign combinations were observed; it does
not mean that every operand pair was tested.
