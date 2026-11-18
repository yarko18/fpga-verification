<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Registered adder functional coverage

`simulation/run_test.py` is the minimal cocotb correctness test and needs only
the default project dependencies.

`simulation/run_coverage.py` is a separate functional-coverage demo. From the
repository root, install the optional dependency and run it with Python 3.11 or
newer:

```bash
python -m pip install -e ".[functional-coverage]"
cd examples/adder_coverage/simulation
python run_coverage.py
```

The demo samples operand signs, their cross, and signed overflow after each
registered result. It prints the hit bins and writes
`simulation/adder_coverage.xml`. Its 100% target means that all bins declared
by this small coverage model were hit; it does not mean that every pair of
4-bit operands was tested.
