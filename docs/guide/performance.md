<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Stream performance

Functional correctness answers whether the output is right. Performance
metrics answer when it arrived and whether the pipeline can sustain traffic.

`PacketObservation` pairs one logical packet at the DUT input and output. The
captured `AvalonSTFrame` timestamps and useful beat count are enough to derive:

- input stalls and output bubbles;
- input and output efficiency;
- SoP, EoP, and end-to-end latency;
- gaps and overlaps between packets;
- the maximum number of packets in flight;
- the clock multiplier required to match an ideal one-beat-per-cycle stream.

```python
analyzer = await StreamPerformanceAnalyzer.from_clock(dut.clk)

observation = PacketObservation(
    name="video[0]",
    beats=useful_beats,
    input_frame=input_frame,
    output_frame=output_frame,
)
metrics = analyzer.packet(observation)
```

For a representative throughput test, queue the sequence before transmission,
keep the output ready, and measure a long stable interval in one clock domain.
`beats` counts accepted transfers, not bytes or payload symbols.

The
[performance notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/10_stream_performance_metrics.ipynb)
documents sequence metrics and regression assertions.

Next: [add control and memory interfaces](control-and-memory.md).
