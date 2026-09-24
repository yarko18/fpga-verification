<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Intel streaming DMA

The Intel DMA helpers model the streaming command, response and data boundary
of Intel read and write DMA components. They do not model the internal FIFO or
Avalon-MM implementation.

```text
RDMA command -> IntelDMABFM -> read data + RDMA response -> DUT
WDMA command + write data -> IntelDMABFM -> WDMA response
                                      |
                               SparseByteMemory
```

All public classes are available from one package:

```python
from fpga_verification.sim.bfms import (
    DMAAddressRegion,
    IntelDMABFM,
    IntelDMACommandMonitor,
    ReadDMADescriptor,
    SparseByteMemory,
    WriteDMADescriptor,
)
```

For a testbench-level example, see [Avalon-MM and DMA](../../guide/control-and-memory.md).

## `DMAAddressRegion`

```python
region = DMAAddressRegion(name="input", start=0x1000, size=0x4000)
```

An address region names one allowed half-open DMA interval. It is used by
`IntelDMACommandMonitor` and can also be used directly in test assertions.

| Member | Meaning |
| --- | --- |
| `name` | Label printed in diagnostics. |
| `start` | First allowed byte address. |
| `size` | Region size in bytes. A negative size raises `ValueError`. |
| `end` | Read-only property equal to `start + size`; this address is excluded. |
| `contains(address, length)` | True when `length` is non-negative and the complete interval `[address, address + length)` fits inside the region. |

The dataclass is immutable. Its string form includes the name and hexadecimal
half-open range, for example `input[0x1000..0x5000)`.

## `SparseByteMemory`

`SparseByteMemory()` is a byte-addressed backing store shared by read and write
DMA paths. Only written addresses consume dictionary entries, which makes it
suitable for large simulated address spaces.

| Method | Behavior |
| --- | --- |
| `write(address, data)` | Writes an iterable of byte values at consecutive addresses. Each value is masked to eight bits. |
| `read(address, length)` | Returns exactly `length` bytes. Every unwritten address reads as zero. |

Reads return a new immutable `bytes` object. The class provides no allocation
or overlap policy; use `DMAAddressRegion` and `IntelDMACommandMonitor` when a
test needs address validation.

```python
memory = SparseByteMemory()
memory.write(0x1000, bytes.fromhex("11223344"))

assert memory.read(0x1000, 4) == bytes.fromhex("11223344")
assert memory.read(0x0FFE, 4) == bytes.fromhex("00001122")
```

Pass the same memory instance to all BFMs that must observe one external
address space.

## `ReadDMADescriptor`

`ReadDMADescriptor` is an immutable decoded read-command value:

```python
descriptor = ReadDMADescriptor.decode(command_word)
```

| Field | Type | Meaning |
| --- | --- | --- |
| `address` | `int` | 64-bit byte address assembled from the low and high address fields. |
| `length` | `int` | Requested byte count. |
| `channel` | `int` | Channel copied to generated read-data beats. |
| `generate_sop` | `bool` | Requests `startofpacket` on read data. |
| `generate_eop` | `bool` | Requests `endofpacket` on read data. |
| `stop` | `bool` | Software-stop command. |
| `reset` | `bool` | Software-reset command. |

### Read command layout

| Bits | Width | Field | Decoded by `ReadDMADescriptor` |
| --- | ---: | --- | --- |
| 31:0 | 32 | address | yes, low address bits |
| 63:32 | 32 | length | yes |
| 71:64 | 8 | channel | yes |
| 72 | 1 | generate SOP | yes |
| 73 | 1 | generate EOP | yes |
| 74 | 1 | software stop | yes |
| 75 | 1 | software reset | yes |
| 83:76 | 8 | programmable burst count | no |
| 99:84 | 16 | stride | no |
| 107:100 | 8 | error | no |
| 108 | 1 | early-done enable | no |
| 140:109 | 32 | address high bits | yes |

Burst count, stride, error and early-done fields are outside the current model
and do not appear in the decoded dataclass.

## `WriteDMADescriptor`

`WriteDMADescriptor` is the immutable write-command counterpart:

```python
descriptor = WriteDMADescriptor.decode(command_word)
```

| Field | Type | Meaning |
| --- | --- | --- |
| `address` | `int` | 64-bit destination byte address. |
| `length` | `int` | Number of stream bytes to store. |
| `end_on_eop` | `bool` | Decoded end-on-EOP request. The current BFM still terminates from `length`. |
| `stop` | `bool` | Software-stop command. |
| `reset` | `bool` | Software-reset command. |

### Write command layout

| Bits | Width | Field | Decoded by `WriteDMADescriptor` |
| --- | ---: | --- | --- |
| 31:0 | 32 | address | yes, low address bits |
| 63:32 | 32 | length | yes |
| 64 | 1 | end on EOP enable | yes |
| 66 | 1 | software stop | yes |
| 67 | 1 | software reset | yes |
| 75:68 | 8 | programmable burst count | no |
| 91:76 | 16 | stride | no |
| 123:92 | 32 | address high bits | yes |

Programmable burst count and stride do not affect the current model.

## `IntelDMACommandMonitor`

`IntelDMACommandMonitor` passively decodes read and write command streams. It
records every observed descriptor and can fail immediately when a normal DMA
transfer lies outside its allowed regions.

```python
monitor = IntelDMACommandMonitor(
    clock=dut.clk,
    reset=dut.reset,
    rdma_cmd_bus=rdma_command_bus,
    wdma_cmd_bus=wdma_command_bus,
    read_address_regions=[DMAAddressRegion("input", 0x1000, 0x4000)],
    write_address_regions=[DMAAddressRegion("output", 0x8000, 0x4000)],
).start()
```

### Constructor arguments

| Argument | Default | Meaning |
| --- | --- | --- |
| `clock` | required | Command-stream clock. |
| `reset` | `None` | Optional active-high reset passed to internally created monitors. |
| `rdma_cmd_bus` | `None` | Read-command `AvalonSTBus`. Omit to disable read observation when no prebuilt monitor is supplied. |
| `wdma_cmd_bus` | `None` | Write-command `AvalonSTBus`. Omit to disable write observation when no prebuilt monitor is supplied. |
| `rdma_cmd_monitor` | `None` | Optional prebuilt passive monitor. It takes precedence over `rdma_cmd_bus`. |
| `wdma_cmd_monitor` | `None` | Optional prebuilt passive monitor. It takes precedence over `wdma_cmd_bus`. |
| `read_address_regions` | `None` | Iterable of allowed read regions. `None` disables read-address checks; an empty iterable rejects every normal read. |
| `write_address_regions` | `None` | Iterable of allowed write regions with the same semantics. |
| `logger` | default cocotb logger | Optional logger instance. |

Internally created monitors use non-packet mode and decode one command beat at
a time.

### Public state and lifecycle

| API | Behavior |
| --- | --- |
| `read_descriptors` | List of read descriptors in observed order. |
| `write_descriptors` | List of write descriptors in observed order. |
| `start()` | Starts enabled command-monitor tasks, is idempotent while running and returns `self`. |
| `stop()` | Cancels monitor tasks. It also cancels passive monitors created internally; injected monitors remain owned by their caller. |

For a checked command, the complete byte interval must fit inside one allowed
region. Reset, stop and zero-length descriptors are control commands and skip
the region check. A violation raises `AssertionError` with the interface name,
simulation time, descriptor address and length, and the allowed ranges.

The command monitor observes policy only. It does not produce data or DMA
responses; use `IntelDMABFM` for that behavior.

## `IntelDMABFM`

`IntelDMABFM` is an active replacement for the exported interfaces of Intel
read DMA, write DMA or both. It consumes commands from the DUT, moves bytes to
or from `SparseByteMemory`, and sends completion responses.

```python
dma = IntelDMABFM(
    dut=dut,
    clock=dut.clk,
    reset=dut.reset,
    memory=memory,
    mode="full",
    read_response_delay_cycles=2,
    write_response_delay_cycles=2,
).start()
```

### Constructor arguments

| Argument | Default | Meaning |
| --- | --- | --- |
| `dut` | required | DUT handle used for logging and default prefix lookup. |
| `clock` | required | Clock shared by the modeled DMA interfaces. |
| `reset` | required | Reset passed to Avalon-ST source and sink objects. |
| `memory` | new `SparseByteMemory` | Shared byte-addressed backing store. |
| `read_response_delay_cycles` | 2 | Clocks between an accepted read command/data enqueue and its response. Must be non-negative. |
| `write_response_delay_cycles` | 2 | Clocks between receiving the write payload and committing memory/responding. Must be non-negative. |
| `mode` | `"full"` | Enables both directions, read only or write only. |
| `rdma_cmd_bus`, `rdma_resp_bus` | prefix lookup | Explicit read command and response buses. |
| `wdma_cmd_bus`, `wdma_resp_bus` | prefix lookup | Explicit write command and response buses. |
| `din_bus`, `dout_bus` | prefix lookup | Explicit read-data output and write-data input buses. |

Accepted mode spellings are:

| Direction | Values |
| --- | --- |
| Read and write | `full`, `read_write`, `readwrite` |
| Read only | `read`, `read_only`, `readonly` |
| Write only | `write`, `write_only`, `writeonly` |

Hyphens and spaces in a mode are normalized to underscores. Any other value
raises `ValueError`.

When explicit buses are omitted, the BFM resolves `rdma_cmd`, `rdma_resp`,
`wdma_cmd`, `wdma_resp`, `din` and `dout` prefixes on `dut`. Data bus widths
must be byte aligned. The read-data bus must expose packet boundary signals
because normal read descriptors are modeled as packets.

Both data paths use eight-bit symbols with the first stream symbol in the
highest-order byte lane. A read maps increasing memory addresses to stream
symbols in that order; a write performs the inverse mapping into memory.

### Read path

For each accepted read descriptor the BFM:

1. decodes and appends it to `read_commands`;
2. handles reset or stop as a control response;
3. for a normal nonzero request, reads `length` bytes from memory and queues
   one packet on `din` with the descriptor channel;
4. schedules the read response after `read_response_delay_cycles`;
5. appends the completed descriptor to `read_responses` when the response is
   queued.

Normal read length must be divisible by `read_data_bytes_per_beat`, because the
modeled `din` interface has no `empty` signal. Both `generate_sop` and
`generate_eop` must be set. Violations raise `RuntimeError` with address,
length, interface and simulation time.

The response delay is independent of when the DUT consumes queued `din` data.
This represents a DMA whose internal FIFO can already contain the payload while
the downstream interface is stalled.

### Write path

For each accepted write descriptor the BFM:

1. decodes and appends it to `write_commands`;
2. handles reset or stop without consuming data;
3. otherwise receives `ceil(length / write_data_bytes_per_beat)` beats from
   `dout` and truncates the final beat to exactly `length` bytes;
4. waits `write_response_delay_cycles`, commits the payload to memory and
   sends a response;
5. appends the completed descriptor to `write_responses`.

Write completion is length driven. The decoded `end_on_eop` flag does not
change payload termination in the current model.

### Response layouts

#### Read response

| Bits | Width | Field |
| --- | ---: | --- |
| 0 | 1 | flush |
| 1 | 1 | stopped |
| 2 | 1 | done strobe |
| 3 | 1 | early-done strobe |

The model emits `0x1` for reset, `0x2` for stop and `0xC` for normal
completion.

#### Write response

| Bits | Width | Field |
| --- | ---: | --- |
| 31:0 | 32 | actual bytes transferred |
| 32 | 1 | reset delayed |
| 33 | 1 | stop state |
| 41:34 | 8 | response error |
| 42 | 1 | early termination |
| 43 | 1 | done strobe |

For a normal write the model sets `done_strobe` and places the requested length
in `actual bytes transferred`. The current control-response encodings are
`0x0000000200000000` for reset and `0x0000000400000000` for stop.

### Public objects and queues

Only objects for directions enabled by `mode` are created.

| Attribute | Meaning |
| --- | --- |
| `memory` | The backing `SparseByteMemory`. |
| `rdma_cmd_sink`, `wdma_cmd_sink` | Command-stream sinks. |
| `rdma_resp_source`, `wdma_resp_source` | Response-stream sources. |
| `din_source` | Read-data source; set `pause` to create gaps in read-data `valid`. |
| `dout_sink` | Write-data sink; set `pause` to apply write-data backpressure. |
| `read_commands`, `write_commands` | Cocotb queues populated as descriptors are accepted. |
| `read_responses`, `write_responses` | Cocotb queues populated when completion responses are queued. Queue items are descriptors, not raw response words. |
| `read_data_bytes_per_beat`, `write_data_bytes_per_beat` | Resolved data widths in bytes for enabled directions. |
| `data_bytes_per_beat` | Read width when read is enabled, otherwise the write width. |

`start()` launches the selected read and write workers and returns `self`.
Repeated calls while running are harmless. `stop()` cancels workers and all
owned Avalon-ST objects; treat it as final teardown for that instance.

Address-region policy is intentionally separate. `IntelDMABFM` executes a
descriptor at any address represented by `SparseByteMemory`; attach an
`IntelDMACommandMonitor` when the test must constrain legal ranges.

## Combined example

```python
from cocotbext.avalon import AvalonSTBus

memory = SparseByteMemory()
memory.write(0x1000, bytes(range(16)))

dma = IntelDMABFM(
    dut,
    clock=dut.clk,
    reset=dut.reset,
    memory=memory,
    mode="full",
).start()

monitor = IntelDMACommandMonitor(
    clock=dut.clk,
    reset=dut.reset,
    rdma_cmd_bus=AvalonSTBus.from_prefix(dut, "rdma_cmd"),
    wdma_cmd_bus=AvalonSTBus.from_prefix(dut, "wdma_cmd"),
    read_address_regions=[DMAAddressRegion("input", 0x1000, 0x1000)],
    write_address_regions=[DMAAddressRegion("output", 0x8000, 0x1000)],
).start()

try:
    # Drive the DUT operation through its public control interface.
    completed_write = await dma.write_responses.get()
    result = memory.read(completed_write.address, completed_write.length)
finally:
    monitor.stop()
    dma.stop()
```
