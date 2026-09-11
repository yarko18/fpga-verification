<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Avalon-ST

After the simulator is running, Avalon-ST helpers provide the first reusable
connection to a streaming DUT. `AvalonFormat` describes how symbols occupy the
`data` word; source, sink, and monitor objects implement clocked transfers.

```text
AvalonSTSource -> valid/data/SOP/EOP -> DUT -> AvalonSTSink
                                             AvalonSTMonitor
```

A beat transfers when the configured `valid`/`ready` condition succeeds.
`AvalonSTFrame` groups accepted beats into a packet and preserves sideband
metadata such as `channel`, `error`, and `empty`.

```python
from cocotbext.avalon import (
    AvalonFormat,
    AvalonSTBus,
    AvalonSTFrame,
    AvalonSTSink,
    AvalonSTSource,
)

fmt = AvalonFormat(bits_per_symbol=8, symbols_per_beat=1)

source = AvalonSTSource(
    AvalonSTBus.from_prefix(dut, "sink"), fmt, dut.clk, reset=dut.reset,
)
sink = AvalonSTSink(
    AvalonSTBus.from_prefix(dut, "source"), fmt, dut.clk, reset=dut.reset,
)

await source.send(AvalonSTFrame([0x11, 0x22, 0x33]))
received = await sink.recv()
```

Sources can insert idle cycles; sinks can apply backpressure. Monitors observe
the same accepted transfers without owning stimulus. Packet mode additionally
uses `startofpacket`, `endofpacket`, and `empty` to reconstruct boundaries and
the valid symbols of the final beat.

Keep wire timing here and payload meaning in a codec above this layer. The next
chapter applies that separation to Intel video streams.

See the
[Avalon-ST notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/03_avalon_st_bus.ipynb)
for ready latency, pauses, beat-level access, and reset behavior.

Next: [Intel video packets](intel-video.md).
