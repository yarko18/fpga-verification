<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Avalon-ST BFM

`AvalonSTSource` drives an Avalon Streaming interface from testbench frames.
`AvalonSTSink` owns `ready`, captures accepted transfers and returns complete
frames or individual beats. Both classes are provided by the installed
`cocotbext.avalon` dependency and are the stream BFMs used by
`fpga-verification` agents and the Intel DMA model.

![](./media/schema.drawio::Page-1)

A transfer is accepted on a rising clock edge when both `valid` and `ready`
are high. The source owns `valid`, `data` and packet sidebands; the sink owns
`ready`. While `valid` is high and `ready` is low, the source keeps the current
beat stable. In packet mode, accepted beats from `startofpacket` through
`endofpacket` form one frame.

```python
from cocotbext.avalon import (
    AvalonFormat,
    AvalonSTBeat,
    AvalonSTBus,
    AvalonSTFrame,
    AvalonSTMonitor,
    AvalonSTSink,
    AvalonSTSource,
)
```

For an end-to-end testbench flow, see the
[video-packet tutorial](../../tutorial/stream-pipeline.md).

## Shared interface description

### `AvalonSTBus`

Create a bus from signals that share a prefix:

```python
input_bus = AvalonSTBus.from_prefix(dut, "din")
output_bus = AvalonSTBus.from_prefix(dut, "dout")
```

`data` is required. The bus detects `valid`, `ready`, `startofpacket`,
`endofpacket`, `empty`, `error` and `channel` when those signals exist. The
source drives source-owned signals; the sink drives `ready` and samples the
remaining signals.

### `AvalonFormat`

```python
fmt = AvalonFormat(
    bits_per_symbol=8,
    symbols_per_beat=4,
    first_symbol_in_high_order_bits=False,
)
```

| Argument | Meaning |
| --- | --- |
| `bits_per_symbol` | Width of one logical symbol. Must be a positive integer. |
| `symbols_per_beat` | Number of symbols packed into one `data` transfer. Must be positive. |
| `first_symbol_in_high_order_bits` | Places the first logical symbol in the most-significant lanes when true and in the least-significant lanes when false. |

`fmt.payload_width` must equal the HDL `data` width. Use the same format for
the source, sink, monitor and any packet codec connected to an interface.

### `AvalonSTFrame`

`AvalonSTFrame(data, channel=None, error=None, empty=None, tx_complete=None)` is
the logical item accepted by a source and returned by `sink.recv()`.

| Field | Meaning |
| --- | --- |
| `data` | Iterable of logical symbols. `bytes` and `bytearray` are converted to integer symbols. |
| `channel` | Constant channel value or a list/tuple selected as symbols are transmitted. |
| `error` | Constant error value or a list/tuple selected as symbols are transmitted. |
| `empty` | Number of unused symbols in the final received beat. The source derives this value from `data` length. |
| `tx_complete` | Cocotb `Event` or callback invoked when source transmission finishes or an in-flight frame is flushed by reset. |
| `sim_time_start`, `sim_time_end` | Simulation timestamps populated by the source or receiver. |

### `AvalonSTBeat`

`AvalonSTBeat` represents one accepted bus transfer. `recv_beat()` returns it
when a test needs packed `data`, unpacked `symbols`, packet flags, sidebands or
the exact transfer timestamp. Use `AvalonSTFrame` for payload-level checks and
`AvalonSTBeat` for protocol-level checks.

## Common constructor arguments

The source and sink share these arguments:

| Argument | Default | Meaning |
| --- | --- | --- |
| `bus` | required | `AvalonSTBus` connected to the HDL interface. |
| `fmt` | required | `AvalonFormat` matching the `data` width. |
| `clock` | required | Transfer clock. |
| `reset` | `None` | Optional reset signal. |
| `reset_active_level` | `True` | Active reset level. Set false for active-low reset. |
| `ready_latency` | 0 | Supported values are 0 and 1. |
| `ready_allowance` | same as `ready_latency` | Supported pairs are `(0, 0)` and `(1, 1)`. |
| `packets` | `None` | Auto-detects packet mode from `startofpacket` and `endofpacket`; true requires both signals; false treats every accepted beat as a frame. |
| `strict_ready_latency` | `False` | For an RL=1 receiver, rejects `valid` when raw `ready` was low in the preceding cycle. |
| `timeout_cycles` | `0` | For a receiver, raises `TimeoutError` after this many clocks without an accepted transfer; zero disables the timeout. |

The constructor starts reset handling immediately. When a reset signal is
provided, transfer processing runs after reset is released. No separate
`start()` call is required.

## `AvalonSTSource`

```python
source = AvalonSTSource(
    bus=input_bus,
    fmt=fmt,
    clock=dut.clk,
    reset=dut.reset,
    packets=True,
    idle_value=0,
)
```

The source converts frame symbols into data beats, drives `valid`, holds a beat
stable under backpressure and generates packet sidebands. If the last packet
beat is incomplete, it pads unused lanes with zero and drives `empty`.

### Source-specific argument

| Argument | Default | Meaning |
| --- | --- | --- |
| `idle_value` | `"x"` | Values driven while `valid` is low: `"x"` for unknown, `"random"` for random bits, `0` for all zeroes or any nonzero integer for all ones. |

### Source methods and state

| API | Behavior |
| --- | --- |
| `await send(frame)` | Queues an `AvalonSTFrame` or an iterable of symbols. Waits while configured queue limits report full. |
| `send_nowait(frame)` | Queues immediately and raises `cocotb.queue.QueueFull` when full. |
| `await write(data)` | Alias for `send(data)`. |
| `write_nowait(data)` | Alias for `send_nowait(data)`. |
| `await wait()` | Waits until the transmit queue is empty and no frame is active. |
| `idle()` | Returns true when no queued or active frame remains. |
| `count()`, `empty()`, `clear()` | Inspect or clear queued frames. `clear()` invokes each cleared frame's completion hook. |
| `pause = value` | When true, inserts gaps by deasserting `valid`. |
| `set_pause_generator(iterable)` | Updates `pause` once per clock from the supplied iterable. |
| `clear_pause_generator()` | Stops the current pause generator. |
| `cancel()` | Cancels transfer, reset and pause coroutines. Use during teardown. |

`queue_occupancy_limit_symbols` and `queue_occupancy_limit_frames` default to
`-1`, which disables source queue limits. Set a positive value when the test
must bound queued traffic.

## `AvalonSTSink`

```python
sink = AvalonSTSink(
    bus=output_bus,
    fmt=fmt,
    clock=dut.clk,
    reset=dut.reset,
    packets=True,
)
```

The sink drives `ready` and captures a beat only when the Avalon-ST handshake
completes. In packet mode it collects beats from `startofpacket` through
`endofpacket`, removes lanes marked by final-beat `empty` and queues one
`AvalonSTFrame`. With `packets=False`, every accepted beat becomes one frame.

### Sink methods and state

| API | Behavior |
| --- | --- |
| `await recv()` | Returns the next complete `AvalonSTFrame`. |
| `recv_nowait()` | Returns a queued frame immediately or raises `cocotb.queue.QueueEmpty`. |
| `await recv_beat()` | Returns the next accepted `AvalonSTBeat`, including packed `data`, unpacked `symbols`, sidebands and timestamp. |
| `recv_beat_nowait()` | Immediate beat form; raises `QueueEmpty` when no beat is queued. |
| `await read(count=-1)` | Reads symbols across queued frames. A negative count returns all currently accumulated symbols after waiting for at least one frame. |
| `read_nowait(count=-1)` | Nonblocking symbol-oriented read. |
| `await wait(timeout=0, timeout_unit="ns")` | Waits for receive activity when the frame queue is empty. A nonzero timeout limits that wait. |
| `count()`, `empty()`, `clear()` | Inspect or clear received frame and beat queues. |
| `pause = value` | When true, applies backpressure by deasserting `ready`. |
| `set_pause_generator(iterable)` | Updates sink pause once per clock. |
| `clear_pause_generator()` | Stops the current pause generator. |
| `cancel()` | Cancels receive, reset, signal-monitor and pause coroutines. |

`queue_occupancy_limit_symbols` and `queue_occupancy_limit_frames` can limit
the receive queue. A full or paused sink deasserts `ready` until a frame is
removed or the pause is cleared.

## `AvalonSTMonitor`

`AvalonSTMonitor` uses the same bus, format, packet and ready-timing arguments
as the sink, but it never drives `ready`. It observes transfers already
accepted by the connected source and sink. Its frame and beat receive methods
have the same meaning as the corresponding sink methods.

Use a monitor for scoreboards, coverage and timing measurements. Use a sink
when the testbench must provide `ready` or insert backpressure. Calling
`cancel()` stops the monitor's receive and reset coroutines.

## Ready timing and backpressure

`ready_latency=0, ready_allowance=0` uses the current-cycle `ready` value for
the handshake. With `ready_latency=1, ready_allowance=1`, `ready` asserted in
cycle N qualifies the transfer in cycle N+1. Other combinations raise
`NotImplementedError`.

Use source pause to create bubbles in `valid` and sink pause to create
backpressure:

```python
def pause_pattern():
    while True:
        yield False
        yield False
        yield True

source.set_pause_generator(pause_pattern())
sink.set_pause_generator(pause_pattern())
```

## Errors and reset

Construction fails when the format width does not match `data`, packet mode is
requested without both packet-boundary signals, or an unsupported ready mode
is selected. Receive-side protocol checks reject transfers outside a packet,
duplicate `startofpacket`, invalid `empty` values and related boundary errors
with the bus name and signal snapshot in the exception.

Reset drives source `valid` and sink `ready` low and discards an in-flight
partial transfer. Completed receive frames and source frames still waiting in
their queues remain available. Call `clear()` when a test needs an empty queue
for a new reset epoch, and call `cancel()` during teardown.
