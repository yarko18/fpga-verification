<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Tutorial: verify a video-packet endianness converter

The `stream_pipeline` example has two RTL implementations:

- `stream_pipeline.sv` uses a register stage;
- `stream_pipeline_fifo.sv` uses an Intel `scfifo`.

Both preserve CONTROL and USER packets and reverse valid symbols in every
VIDEO payload beat. With four symbols per beat, `[1, 2, 3, 4, 5]` becomes
`[4, 3, 2, 1, 5]`.

## Test configuration

`simulation/vip/config.py` defines the HDL symbol width and symbols per beat.
The runner passes HDL fields to the compiler and serialises the full config for
the cocotb test, which restores it with `load_runtime_config(TestConfig)`.

## Direct cocotb test

`simulation/vip/test.py` creates `AvalonSTSource` and `AvalonSTSink` using one
`VideoFormat`. It sends three packet types:

```python
input_packets = [
    VIPControlPacket(width=5, height=1),
    VIPUserPacket(user_type=1, payload=[0x11, 0x22, 0x33]),
    VIPVideoPacket([1, 2, 3, 4, 5]),
]
```

The expected packets are explicit. CONTROL and USER remain unchanged; VIDEO is
expected as `VIPVideoPacket([4, 3, 2, 1, 5])`. No model, scoreboard or pyuvm
environment is involved.

## Runners

The regular runner selects `stream_pipeline`:

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.vip.run_test
```

The FIFO runner selects `stream_pipeline_fifo` and asks the RTL runner to load
the simulator-independent `altera_mf` library:

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.vip.run_test_fifo
```

Use `SIM=questa` for Questa. Set `QUARTUS_SIM_LIB` when the Quartus simulation
library cannot be discovered automatically.
