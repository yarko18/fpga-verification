<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Control and memory

Streaming datapaths are often configured through Avalon-MM and may access
external memory through DMA. The library provides separate components for both
roles.

## Avalon-MM control

`AvalonMMMasterBFM` is a lightweight, single-transaction host for register
access. It supports reads, writes, read-modify-write, polling, timeouts,
optional byte enables, and `waitrequest`.

`AvalonMMMonitor` publishes accepted transactions to a pyuvm analysis port so
the same writes that configure the DUT can update a behavior model.
`AvalonMMAgent` combines the passive monitor with an optional active master.

When the DUT is the Avalon-MM master, `AvalonMMMemoryBFM` provides a slave-side
byte-addressed memory and records read and write transfers.

## Intel DMA model

`IntelDMABFM` is a black-box behavioral replacement for Intel streaming DMA
interfaces:

```text
read command  -> model -> stream data + response
write command + stream data -> model -> memory + response
```

`SparseByteMemory` stores only written bytes and returns zero elsewhere.
Descriptor decoders expose address, length, and control fields.
`IntelDMACommandMonitor` can passively record commands and validate their
address ranges.

Use the
[Avalon-MM notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/04_avalon_mm_bus.ipynb)
for control and memory ports, and the
[DMA notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/06_intel_dma_bfm.ipynb)
for descriptor-driven traffic.

Next: [run the same kind of data exchange on hardware](hil.md).
