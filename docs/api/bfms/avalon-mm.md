<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Avalon-MM BFMs

The Avalon-MM BFMs connect cocotb tests to register and memory-mapped ports.
They are provided by the installed `cocotbext.avalon` dependency.

```python
from cocotbext.avalon import (
    AvalonMMBus,
    AvalonMMMasterBFM,
    AvalonMMMemoryBFM,
    AvalonMMSlaveBFM,
    AvalonMMTransaction,
)
```

Use `AvalonMMMasterBFM` when the testbench controls a DUT slave. Use
`AvalonMMMemoryBFM` when the DUT is a master and needs a byte-addressed memory.
Subclass `AvalonMMSlaveBFM` when a slave must implement behavior other than
memory storage.

For a task-oriented control and memory example, see
[Avalon-MM and DMA](../../guide/control-and-memory.md).

## `AvalonMMBus`

`AvalonMMBus` groups the HDL signals used by all Avalon-MM BFMs. `address` is
the only required constructor argument, so the same type can represent
read-only, write-only and read/write interfaces.

```python
bus = AvalonMMBus.from_prefix(dut, "control")
```

`from_prefix()` resolves `control_address`, `control_read`,
`control_writedata` and the other standard `<prefix>_<signal>` names. Missing
optional signals are stored as `None`. Construct the dataclass directly when
the HDL uses other names.

| Signal member | Used for |
| --- | --- |
| `address` | Address driven by a master and sampled by a slave. |
| `write`, `writedata` | Write request and write payload. |
| `read`, `readdata` | Read request and read payload. |
| `waitrequest` | Slave backpressure. If absent, requests are accepted without waiting. |
| `readdatavalid` | Marks a read response. A master can instead use fixed read latency when it is absent. |
| `byteenable` | Enables individual byte lanes. If absent, all lanes are enabled. |
| `burstcount`, `beginbursttransfer` | Optional burst metadata. |
| `response`, `writeresponsevalid` | Optional response signals driven idle by the current slave BFM. |
| `lock`, `debugaccess` | Optional master sidebands driven low by the current master BFM. |
| `label` | Interface name used in log and error messages. |

The bus exposes `address_width`, `write_data_width`, `read_data_width`,
`data_width`, `byteenable_width`, `burstcount_width`, `has_read` and
`has_write` properties derived from the connected signals.

## `AvalonMMTransaction`

`AvalonMMTransaction` is an immutable record of one accepted slave-side beat.

| Field | Meaning |
| --- | --- |
| `kind` | `"read"` or `"write"`. |
| `address` | Address of this beat. |
| `data` | Write data, or `None` for a read request. |
| `byteenable` | Accepted byte-lane mask. |
| `burstcount` | Total number of beats declared for the burst. |
| `beat_index` | Zero-based position of this beat in the burst. |

`AvalonMMMemoryBFM.read_transactions` and `write_transactions` contain these
records when transaction recording is enabled.

## `AvalonMMMasterBFM`

`AvalonMMMasterBFM` performs one register-style access at a time. It supports
read and write handshakes, byte enables, `waitrequest`, `readdatavalid`, fixed
read latency, polling and access timeouts. It does not issue bursts or keep
multiple reads outstanding.

```python
master = AvalonMMMasterBFM.from_prefix(
    dut,
    "control",
    dut.clk,
    reset=dut.reset,
    default_byteenable=0xF,
)
master.start()
```

`start()` initializes master-owned signals. It does not launch a background
task and currently returns `None`.

### Constructor arguments

| Argument | Default | Meaning |
| --- | --- | --- |
| `bus` | required | Bound `AvalonMMBus`. |
| `clock` | required | Interface clock. |
| `reset` | `None` | Optional reset used by `wait_reset_release()`; the master does not drive it. |
| `read_response_latency` | `0` | Additional clocks before sampling `readdata` when `readdatavalid` is absent. Must be non-negative. |
| `default_byteenable` | all lanes | Byte mask used when an access omits `byteenable`. |
| `packet_logging` | `False` | Logs completed accesses when enabled. |
| `packet_log_level` | `logging.INFO` | Numeric level or standard level name. |

### Methods

| API | Behavior |
| --- | --- |
| `start()` | Drives master-owned outputs to their idle values. |
| `await wait_reset_release(active_value=1)` | Waits while the supplied reset equals `active_value`; returns immediately when no reset was supplied. |
| `await write(address, data, byteenable=None, timeout_cycles=None)` | Holds a single write until accepted. |
| `await read(address, byteenable=None, timeout_cycles=None)` | Performs a single read and returns `readdata`. |
| `await read_modify_write(address, update, ...)` | Reads, writes `update(old)` and returns `(old, new)`. |
| `await poll(address, predicate, interval_cycles=1, timeout_cycles=None)` | Repeats reads until `predicate(value)` is true and returns that value. |
| `await wait_set(address, mask, timeout_cycles=None)` | Waits until every bit in `mask` is set. |
| `await wait_clear(address, mask, timeout_cycles=None)` | Waits until every bit in `mask` is clear. |
| `set_packet_logging(enable, level=None)` | Changes access logging at runtime. |

Addresses and write data are checked against their signal widths. A timeout
while waiting for `waitrequest` or `readdatavalid` raises `TimeoutError` with
the interface label and address.

## `AvalonMMSlaveBFM`

`AvalonMMSlaveBFM` accepts DUT master requests in a background cocotb task. It
implements bursts, byte enables, wait-state generation, in-order read
responses and optional transaction recording. The base class has no storage:
a subclass implements `read_word(address, byteenable)` and
`write_word(address, data, byteenable)`.

### Constructor arguments

| Argument | Default | Meaning |
| --- | --- | --- |
| `bus`, `clock`, `reset` | required, required, `None` | Interface signals, clock and optional reset. |
| `read_latency` | `1` | Clock delay before the first read response. Must be non-negative. Queued burst responses follow on consecutive clocks. |
| `reset_active_level` | `True` | Active reset value. |
| `waitrequest_during_reset` | `True` | Drives `waitrequest` while reset is active. |
| `idle_readdata` | `0` | Value driven when no read response is valid. |
| `record_transactions` | `False` | Appends accepted beats to `read_transactions` and `write_transactions`. |
| `packet_logging`, `packet_log_level` | `False`, `logging.INFO` | Controls per-beat logging. |
| `randomize` | `False` | Starts with a random wait-state generator using a 25 percent pause probability. |
| `logger` | interface logger | Optional logger instance. |

### Methods and state

| API | Behavior |
| --- | --- |
| `start()` | Initializes outputs, launches the slave task and returns `self`. Repeated calls while running are harmless. |
| `stop()` | Cancels the slave task. |
| `pause = value` | When true, applies backpressure through `waitrequest`. |
| `set_pause_generator(iterable)` | Updates `pause` once per clock from an iterable. |
| `clear_pause_generator()` | Removes the current pause generator. |
| `set_randomize(enable)` | Selects or removes the built-in random pause generator. |
| `set_packet_logging(enable, level=None)` | Changes accepted-transfer logging. |
| `read_transactions`, `write_transactions` | Recorded `AvalonMMTransaction` lists when recording is enabled. |

For a burst, the BFM treats `address` as the first byte address and increments
subsequent beat addresses by the data width in bytes. `byteenable` bit zero
corresponds to the lowest addressed byte lane.

## `AvalonMMMemoryBFM`

`AvalonMMMemoryBFM` supplies the `AvalonMMSlaveBFM` word methods using an
external byte-addressed memory object. The object must implement this small
protocol:

```python
class ByteMemory:
    def read(self, address: int, length: int) -> bytes: ...
    def write(self, address: int, data) -> None: ...
```

The BFM has no implicit memory capacity. Capacity, valid addresses and
allocation behavior come from the supplied memory object. A read must return
exactly the requested number of bytes. See
[`SparseByteMemory`](dma.md#sparsebytememory) for the unbounded sparse model
provided by `fpga-verification`.

```python
memory_bfm = AvalonMMMemoryBFM.from_prefix(
    dut,
    "memory",
    dut.clk,
    reset=dut.reset,
    memory=memory,
    byteorder="little",
    read_latency=2,
    record_transactions=True,
).start()
```

`byteorder` can be `"little"` or `"big"` and controls conversion between a
bus word and consecutive memory bytes. Disabled read lanes return zero.
Disabled write lanes preserve the corresponding existing memory bytes.

The data width must be byte aligned. When both read and write data signals are
present, their widths must match, and an explicit `byteenable` width must equal
the data width in bytes.
