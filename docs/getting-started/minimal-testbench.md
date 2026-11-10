<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Run the minimal testbench

Start with the simulator-ready example in `examples/stream_pipeline`. One RTL
module reverses byte order inside VIDEO payload beats while forwarding CONTROL
and USER packets unchanged.

```text
examples/stream_pipeline/
  rtl/stream_pipeline.sv
  simulation/
    test_1/
      config.py
      test.py
      run_test.py
    test_2/
      config.py
      test.py
      run_test.py
```

Run it from the repository root:

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.test_1.run_test
```

For Questa:

```bash
SIM=questa python -m examples.stream_pipeline.simulation.test_1.run_test
```

Each teaching project has its own `StreamPipelineTest` base class, which creates
`AvalonSTSource` and `AvalonSTSink` once per cocotb test. Three small subclasses
independently check CONTROL, USER and VIDEO packets against explicit expected
packets. The two projects intentionally duplicate this testbench code so they
remain standalone examples.

The Altera FIFO version uses the same three tests:

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.test_2.run_test
```

The second testbench enables `USE_FIFO` and selects `altera_mf` directly. No
component description or Platform Designer generation is needed. See the
[tutorial](../tutorial/stream-pipeline.md) for the complete flow.
