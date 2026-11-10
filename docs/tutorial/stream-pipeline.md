<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Tutorial: verify a video-packet endianity converter

This example describe IP to swap color plane order in video packet.

- swap color symbols in video packets

- ther packet propagate without changes

The scheme above show simple diagram of proposed IP. Video packet goest through endianity convertor and the rest is just propagated to the output. Also it's possible to insert FIFO for the output stream.

![internal structure](./media/schema.drawio::Page-1)

This is an example how RGB pixels cnverts to BGR format.

![video packet example](./media/schema.drawio::Page-2)


Sources:

- `stream_pipeline.sv`

Interfaces:

- `din`: input data stream
- `dout`: output data stream


Parameters:



 `USE_FIFO=0` selects its register
stage; `USE_FIFO=1` selects an Altera `scfifo`.


Both preserve CONTROL and USER packets and reverse valid symbols in every
VIDEO payload beat. With four symbols per beat, `[1, 2, 3, 4, 5]` becomes
`[4, 3, 2, 1, 5]`.

## Test configuration

`simulation/test_1/config.py` defines the HDL symbol width, symbols per beat and
`USE_FIFO` parameter.
The runner passes HDL fields to the compiler and serialises the full config for
the cocotb test, which restores it with `load_test_config(TestConfig)`.

## Direct cocotb tests

`simulation/testbench.py` defines the common `StreamPipelineTest` base class.
Its only constructor restores the resolved configuration and creates the clock,
`AvalonSTSource`, and `AvalonSTSink` using one `VideoFormat`. It also owns reset,
cleanup, and the common send/receive comparison.

Three subclasses contain only packet-specific stimulus and expectations:

```python
class ControlPacketTest(StreamPipelineTest): ...
class UserPacketTest(StreamPipelineTest): ...
class VideoPacketTest(StreamPipelineTest): ...
```

Each local `test.py` registers these as three independent cocotb tests with its
own `TestConfig`. CONTROL and USER remain unchanged; VIDEO input
`VIPVideoPacket([1, 2, 3, 4, 5])` is expected as
`VIPVideoPacket([4, 3, 2, 1, 5])`. No model, scoreboard, pyuvm environment, or
parameter matrix is involved.

## Runners

`test_1` uses `USE_FIFO=False` and needs no vendor library:

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.test_1.run_test
```

`test_2` has its own config, test and runner. It uses the same RTL, sets
`USE_FIFO=True` and asks the RTL runner to load the simulator-independent
`altera_mf` library:

```bash
SIM=verilator python -m examples.stream_pipeline.simulation.test_2.run_test
```

Use `SIM=questa` for Questa. Set `QUARTUS_SIM_LIB` when the Quartus simulation
library cannot be discovered automatically.
