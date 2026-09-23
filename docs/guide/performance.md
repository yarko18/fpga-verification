<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Stream performance

Functional checking answers whether output content is correct. Performance
metrics answer when it appeared and whether the pipeline sustained traffic.
The calculations are protocol-independent; cocotb normally supplies the real
timestamps.

## Observation model

`PacketObservation` pairs the same logical packet at a DUT input and output.
`beats` is the number of useful accepted transfers. Monitor, source and sink
frames carry `sim_time_start` and `sim_time_end`.

```text
input SoP -------- input EoP
       \---- DUT / pipeline ----                         output SoP -------- output EoP
```

```python
from cocotbext.avalon import AvalonSTFrame
from fpga_verification.sim import PacketObservation

input_frame = AvalonSTFrame([0x10, 0x20, 0x30, 0x40])
output_frame = AvalonSTFrame([0x10, 0x20, 0x30, 0x40])

# A source, sink or monitor normally sets these during simulation.
input_frame.sim_time_start = 100
input_frame.sim_time_end = 130
output_frame.sim_time_start = 120
output_frame.sim_time_end = 160

observation = PacketObservation(
    name="packet_0", beats=4,
    input_frame=input_frame, output_frame=output_frame,
)
```

Do not infer `beats` from payload symbol count when a final beat has empty
symbols. It measures accepted handshakes, not bytes or application values.

## Clock calibration

Metrics are expressed in clock cycles rather than simulator time units. Create
one analyzer after the relevant clock starts. It observes two rising edges and
stores the period; later timestamp differences must be exact multiples of it.

```python
from fpga_verification.sim import StreamPerformanceAnalyzer

analyzer = await StreamPerformanceAnalyzer.from_clock(dut.clk)
```

This check catches observations from unrelated clocks or timestamps captured
between edges.

## Packet metrics

`analyzer.packet(observation)` returns `PacketMetrics`.

| Field | Meaning |
| --- | --- |
| `input_cycles`, `output_cycles` | Inclusive duration of each packet. |
| `input_stalls` | Input duration minus useful beats. |
| `output_bubbles` | Output duration minus useful beats. |
| `input_efficiency`, `output_efficiency` | Useful beats divided by duration. |
| `sop_latency`, `eop_latency` | Input-to-output boundary latency. |
| `end_to_end_cycles` | Input SoP through output EoP, inclusive. |

```python
async def measure_one_packet(clock, input_monitor, output_monitor, beats):
    analyzer = await StreamPerformanceAnalyzer.from_clock(clock)
    input_seen = await input_monitor.recv()
    output_seen = await output_monitor.recv()
    return analyzer.packet(PacketObservation(
        name="packet", beats=beats,
        input_frame=input_seen, output_frame=output_seen,
    ))
```

Use `metrics.log(logger)` to make a regression result readable in the cocotb
log.

## Sequence metrics

`analyzer.sequence(name, observations)` analyses an ordered group of packets.
It includes individual metrics plus packet gaps, start intervals, boundary
overlap, maximum packets in flight and aggregate efficiency.

```python
async def measure_sequence(clock, observations):
    analyzer = await StreamPerformanceAnalyzer.from_clock(clock)
    metrics = analyzer.sequence("stream", observations)

    metrics.assert_input_packet_gap_at_most(2)
    metrics.assert_all_boundaries_overlap()
    print(f"input efficiency: {metrics.input_efficiency:.2%}")
    print(f"output efficiency: {metrics.output_efficiency:.2%}")
    return metrics
```

`sustainable_efficiency` is the smaller of input and output efficiency.
`required_clock_multiplier` is the clock-rate multiplier needed to match an
ideal one-beat-per-cycle stream.

## Recommended workflow

1. Start the DUT clock and create one analyzer for that clock domain.
2. Capture matching input and output frames in input order.
3. Determine useful beat count from the packet format.
4. Create `PacketObservation` objects.
5. Log the metrics and assert the performance contract separately from
   functional output comparison.

Measure a long, representative interval with source traffic queued in advance
and the sink ready unless sink backpressure is part of the requirement. A
performance test that accidentally measures testbench gaps is not a DUT
throughput test.

Next: [add control and memory interfaces](control-and-memory.md).
