<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Run the minimal testbench

The repository contains several verification examples. Start with the complete,
simulator-ready example in `examples/stream_pipeline`. The component accepts an
Intel Avalon-ST Video packet stream and stores one beat. It reverses byte order
inside VIDEO payload beats while forwarding CONTROL and USER packets unchanged.

```text
examples/stream_pipeline/
  rtl/stream_pipeline.sv
  simulation/vip/
    config.py
    layout.py
    functional_model.py
    behavior_model.py
    scoreboard.py
    env.py
    test_pyuvm.py
    run_test.py
  tests/test_models.py
```

Run it from the repository root:

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.vip.run_test
```

For Questa:

```bash
SIM=questa python -m examples.stream_pipeline.simulation.vip.run_test
```

The test sends an ordered control, user, and video packet sequence. The source
monitor creates pass-through expectations for CONTROL and USER packets and
byte-reversed expectations for VIDEO payloads. The sink monitor checks every
output packet against the scoreboard FIFO.

The two model checks run without a simulator:

```bash
python -m pytest -q examples/stream_pipeline/tests
```

Use this example to answer practical questions about imports, relative paths,
phase ordering, reset, and cleanup. The [tutorial](../tutorial/stream-pipeline.md)
explains why each file exists; [Project style](../guide/testbench-style.md) is the
short convention reference.
