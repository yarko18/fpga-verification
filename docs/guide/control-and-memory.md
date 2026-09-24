<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Avalon-MM and DMA

A streaming data path often has a control port and sometimes accesses external
memory. Keep these roles separate from the data-stream agent: control
transactions update the behavior model; memory BFMs model a visible memory
contract; DMA BFMs model command, response and stream traffic.

## Avalon-MM master

`AvalonMMMasterBFM` is a lightweight, single-transaction host. It supports
reads, writes, read-modify-write, polling, timeouts, optional byte enables and
`waitrequest`. It does not issue bursts or multiple outstanding reads.

```python
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotbext.avalon import AvalonMMMasterBFM


@cocotb.test()
async def control_register_test(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    avmm = AvalonMMMasterBFM.from_prefix(
        dut, "control", dut.clk, reset=dut.reset,
        default_byteenable=0xF,
    ).start()

    dut.reset.value = 1
    await RisingEdge(dut.clk)
    dut.reset.value = 0
    await avmm.wait_reset_release(active_value=1)

    await avmm.write(0x00, 0x00000001, timeout_cycles=32)
    status = await avmm.read(0x04, timeout_cycles=32)
    await avmm.wait_set(0x04, 0x1, timeout_cycles=256)
    assert status & 0x1 in (0, 1)
```

Manual construction is useful when signal names do not share a prefix.

```python
from cocotbext.avalon import AvalonMMBus, AvalonMMMasterBFM

bus = AvalonMMBus(
    address=dut.ctrl_address,
    writedata=dut.ctrl_writedata,
    write=dut.ctrl_write,
    read=dut.ctrl_read,
    readdata=dut.ctrl_readdata,
    waitrequest=getattr(dut, "ctrl_waitrequest", None),
    readdatavalid=getattr(dut, "ctrl_readdatavalid", None),
    byteenable=getattr(dut, "ctrl_byteenable", None),
)
avmm = AvalonMMMasterBFM(bus, dut.clk, reset=dut.reset)
```

Convenience operations keep a test's intent visible:

```python
async def configure_component(avmm):
    old, new = await avmm.read_modify_write(
        0x00, lambda value: value | 0x1, timeout_cycles=32,
    )
    status = await avmm.poll(
        0x04, lambda value: value & 0x1,
        interval_cycles=2, timeout_cycles=256,
    )
    return old, new, status
```

## Slave and memory BFMs

When the DUT is an Avalon-MM master, `AvalonMMMemoryBFM` exposes a
byte-addressed memory. `SparseByteMemory` has no configured size: it stores
only written addresses and reads zero from untouched addresses. See the
[memory API](../api/bfms/dma.md#sparsebytememory) for its allocation and
capacity semantics.

```python
from cocotbext.avalon import AvalonMMMemoryBFM
from fpga_verification.sim.bfms import SparseByteMemory


def make_memory_slave(dut):
    memory = SparseByteMemory()
    memory.write(0x1000, bytes.fromhex("44332211"))
    slave = AvalonMMMemoryBFM.from_prefix(
        dut, "memory", dut.clk, reset=dut.reset,
        memory=memory, byteorder="little", read_latency=2,
        record_transactions=True, randomize=True,
    ).start()
    return memory, slave
```

Byte enables apply per byte lane. In little-endian order lane zero is the
lowest addressed byte. With `record_transactions=True`, read and write lists
contain `AvalonMMTransaction` records with kind, address, data, byteenable,
burst count and beat index.

`AvalonMMMonitor` publishes accepted transactions to a pyuvm analysis port.
`AvalonMMAgent` packages the passive monitor with an optional active master.
Connect that port to the custom scoreboard so model state changes in exactly
the order the DUT observed them.

```python
from fpga_verification.sim.agents import AvalonMMAgent

control_agent = AvalonMMAgent(
    "control_agent", parent,
    bus=AvalonMMBus.from_prefix(dut, "control"),
    clock=dut.clk, reset=dut.reset, packet_logging=True,
)
```

## DMA model

`IntelDMABFM` is a black-box behavioral replacement for Intel streaming DMA
interfaces. It models externally observable transactions, not internal FIFOs
or Avalon-MM implementation details.

```text
read command  -> IntelDMABFM -> input data + read response -> DUT
write command + output data -> IntelDMABFM -> write response
                                         |
                                   SparseByteMemory
```

Descriptors are immutable decoded objects. Address regions give the command
monitor an explicit allowed half-open range `[start, end)`.

```python
from fpga_verification.sim.bfms import (
    DMAAddressRegion,
    ReadDMADescriptor,
    SparseByteMemory,
    WriteDMADescriptor,
)

memory = SparseByteMemory()
memory.write(0x1000, bytes([1, 2, 3, 4]))
print(memory.read(0x0FFE, 8))

region = DMAAddressRegion("input", start=0x1000, size=0x100)
assert region.contains(0x1080, 16)
assert not region.contains(0x10F8, 16)

read_word = 0x1000 | (16 << 32) | (3 << 64) | (1 << 72) | (1 << 73)
write_word = 0x8000 | (16 << 32) | (1 << 64)
print(ReadDMADescriptor.decode(read_word))
print(WriteDMADescriptor.decode(write_word))
```

In `full` mode the BFM owns both paths; `read` and `write` modes select one.
The default prefixes are `rdma_cmd`, `rdma_resp`, `wdma_cmd`, `wdma_resp`,
`din` and `dout`, but explicit `AvalonSTBus` objects can be supplied.

```python
from fpga_verification.sim.bfms.intel_dma import IntelDMABFM, IntelDMACommandMonitor
from cocotbext.avalon import AvalonSTBus

memory = SparseByteMemory()
dma = IntelDMABFM(
    dut, clock=dut.clk, reset=dut.reset, memory=memory, mode="full",
).start()

command_monitor = IntelDMACommandMonitor(
    clock=dut.clk,
    reset=dut.reset,
    rdma_cmd_bus=AvalonSTBus.from_prefix(dut, "rdma_cmd"),
    wdma_cmd_bus=AvalonSTBus.from_prefix(dut, "wdma_cmd"),
    read_address_regions=[DMAAddressRegion("input", 0x1000, 0x4000)],
    write_address_regions=[DMAAddressRegion("output", 0x8000, 0x4000)],
).start()

try:
    # Drive DUT-specific control and wait for its observable result.
    written = memory.read(0x8000, 16)
finally:
    dma.stop()
    command_monitor.stop()
```

For a normal read descriptor the model reads memory, sends a packet with the
requested channel and schedules a completion response. Read length must align
to the exported data beat because that interface has no `empty` signal in this
model. For a write descriptor it collects enough beats, truncates the last
beat to the requested byte length, commits memory and responds.

`read_response_delay_cycles` and `write_response_delay_cycles` control response
timing. `dma.din_source.pause` delays produced data; `dma.dout_sink.pause`
creates write-side backpressure. Public command and response queues allow a
test to wait for accepted or completed operations.

Always call `stop()` in teardown or a `finally` block. The model validates
negative response delays, malformed packet flags, unaligned reads and addresses
outside configured regions with contextual errors.
