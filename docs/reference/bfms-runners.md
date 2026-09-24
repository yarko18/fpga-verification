<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# BFMs and runners API

The reference is split by interface and responsibility. Use the how-to guides
for complete testbench flows and these chapters for constructor arguments,
public methods, state and modeled protocol behavior.

## Bus functional models

- [Avalon-ST source and sink](bfms/avalon-st.md) describes stream formatting,
  `AvalonSTSource`, `AvalonSTSink`, packet and beat queues, backpressure, reset
  and cleanup.
- [Intel streaming DMA](bfms/intel-dma.md) describes `IntelDMABFM`, its command
  monitor, descriptors, allowed address regions and shared sparse memory.

## Simulation runners

- [Runners](runners.md) contains the API for plain RTL, generated Intel
  components and Platform Designer systems.

For task-oriented examples, see [Avalon-ST](../guide/avalon-st.md),
[Avalon-MM and DMA](../guide/control-and-memory.md) and
[Simulation runners](../sim/runners.md).
