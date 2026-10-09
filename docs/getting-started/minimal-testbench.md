<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Run the minimal testbench

Start with the simulator-ready example in `examples/stream_pipeline`. Both RTL
variants reverse byte order inside VIDEO payload beats while forwarding CONTROL
and USER packets unchanged.

```text
examples/stream_pipeline/
  rtl/
    stream_pipeline.sv
    stream_pipeline_fifo.sv
  simulation/vip/
    config.py
    test.py
    run_test.py
    run_test_fifo.py
```

Run it from the repository root:

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.vip.run_test
```

For Questa:

```bash
SIM=questa python -m examples.stream_pipeline.simulation.vip.run_test
```

The direct cocotb test sends CONTROL, USER and VIDEO packets through
`AvalonSTSource`, receives them through `AvalonSTSink` and compares them with
explicit expected packets.

The Intel FIFO version uses the same test:

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.vip.run_test_fifo
```

Its runner selects `altera_mf` directly, without a component description or
Platform Designer generation. See the
[tutorial](../tutorial/stream-pipeline.md) for the complete flow.
