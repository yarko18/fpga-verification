<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# BFMs and runners API

The API documentation is split by interface and responsibility. These chapters
describe constructor arguments, public methods, state and modeled protocol
behavior.

## Bus functional models

- [Avalon-ST BFM](bfms/avalon-st.md) describes stream formatting, source, sink,
  monitor, packet and beat queues, backpressure, reset and cleanup.
- [Avalon-MM BFM](bfms/avalon-mm.md) describes the bus bundle, master, slave,
  memory model and recorded transactions.
- [DMA BFM](bfms/dma.md) describes `IntelDMABFM`, its command monitor,
  descriptors, address regions and `SparseByteMemory`.

## Simulation runners

- [Runners](runners.md) contains the API for plain RTL, generated Intel
  components and Platform Designer systems.

For task-oriented examples, see the
[video-packet tutorial](../tutorial/stream-pipeline.md),
[Avalon-MM and DMA](../guide/control-and-memory.md) and
[simulation runners](../sim/runners.md).
