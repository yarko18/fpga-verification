<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# VIP verification

The behavior model predicts what the DUT should do. VIP verification turns
that prediction into an ordered contract for the output stream.

```text
VIPSequence -> source driver -> DUT -> sink monitor
                    |                    |
             source monitor             |
                    +----> custom scoreboard
                                |
                         behavior model
                                |
                    ordered expectation queue
```

`VIPSequence` sends `VIPItem` objects through an active `VIPAgent`. The source
and sink monitors publish decoded packets through pyuvm analysis ports. The
custom scoreboard consumes them and adds `PacketExpectation` objects to
`BaseVIPScoreboard`.

## `VIPAgent`: drive, observe, publish

`VIPAgent` is the pyuvm component around one Intel Avalon-ST Video path. It
creates the protocol-specific objects from buses and formats; it does not
predict DUT behavior. Give it at least one of `source_bus` or `sink_bus`.

| Bus supplied | Always created | Created in active mode |
| --- | --- | --- |
| `source_bus` | `source_monitor` | Avalon-ST source, `VIPDriver`, `sequencer` |
| `sink_bus` | `sink_monitor` | Sink monitor drives `ready` |

An active agent (`UVM_ACTIVE`, the default) can send a `VIPSequence` through
`source_bus` and provides backpressure on `sink_bus`. A passive agent
(`UVM_PASSIVE`) only reconstructs and publishes traffic already driven by the
DUT or another testbench component. It creates no source driver or sequencer
and never drives `ready`.

```python
from pyuvm import uvm_active_passive_enum
from cocotbext.avalon import AvalonSTBus
from fpga_verification.sim.agents import VIPAgent


active_agent = VIPAgent(
    "data_agent",
    parent,
    clock=dut.clk,
    reset=dut.reset,
    source_bus=AvalonSTBus.from_prefix(dut, "din"),
    sink_bus=AvalonSTBus.from_prefix(dut, "dout"),
    source_fmt=layout.input_format,
    sink_fmt=layout.output_format,
    reset_active_level=True,
    ready_latency=0,
    ready_allowance=None,
    idle_value=0,
    randomize=False,
    packet_logging=True,
)

passive_tap = VIPAgent(
    "output_tap",
    parent,
    clock=dut.clk,
    reset=dut.reset,
    sink_bus=AvalonSTBus.from_prefix(dut, "dout"),
    sink_fmt=layout.output_format,
    is_active=uvm_active_passive_enum.UVM_PASSIVE,
)
```

`source_fmt` is required with `source_bus`; `sink_fmt` is required with
`sink_bus`. When both stream formats are identical, `sink_fmt` defaults to
`source_fmt`.

### Send packet objects through the sequencer

`VIPItem` contains exactly one complete VIP packet. `VIPSequence.from_packets()`
converts an ordered packet list into items; the active agent's `VIPDriver`
serialises each packet to an `AvalonSTFrame`.

```python
from fpga_verification.sim.agents import VIPSequence

packets = [
    input_codec.control_packet(frame_size),
    input_codec.frame_to_video_packet(frame, frame_size),
]
sequence = VIPSequence.from_packets(packets, name="input_frame")
await sequence.start(active_agent.sequencer)
```

Keep control, user and video packets as separate sequence items. Packet
boundaries then remain visible to the driver, source monitor and scoreboard.
A passive agent has no sequencer; attempting to use one is a testbench
configuration error.

### Analysis ports and `AnalysisImp`

Both monitor accessors return ordinary pyuvm analysis ports:

- `source_analysis_port` publishes decoded packets accepted at `source_bus`;
- `sink_analysis_port` publishes decoded packets accepted at `sink_bus`.

Accessing a port whose corresponding bus was not supplied raises a `RuntimeError`.
Connect ports in the environment's `connect_phase()` to exports owned by the
scoreboard.

```python
def connect_phase(self):
    if self.scoreboard.data_in_export is not None:
        self.data_agent.source_analysis_port.connect(
            self.scoreboard.data_in_export,
        )
    self.data_agent.sink_analysis_port.connect(
        self.scoreboard.data_out_export,
    )
    self.control_agent.analysis_port.connect(
        self.scoreboard.control_export,
    )
```

`AnalysisImp` is the adapter from `uvm_analysis_port.write(item)` to a Python
callback. `BaseVIPScoreboard` creates three instances:

```text
source_analysis_port.write(packet)
  -> data_in_export.write(packet)
  -> _process_input_packet(packet)
  -> process_input_packet(packet)*
  -> add_expectation(...)

sink_analysis_port.write(packet)
  -> data_out_export.write(packet)
  -> _process_output_packet(packet)
  -> compare packet with expected_queue[0]

control_agent.analysis_port.write(transaction)
  -> control_export.write(transaction)
  -> _process_control_transaction(transaction)
  -> process_control_transaction(transaction)*
  -> behavior_model.process_register_write(...)
```

The underscored callbacks are library wrappers: they ignore traffic while reset
is active, capture exceptions as sticky scoreboard failures, and then invoke
the corresponding public hook. The `*` hooks are implemented by the custom
scoreboard for the concrete IP.

### Timing randomisation, logging and cleanup

`randomize=True` applies pause generators to the active source and to the
active sink's `ready` path. Enable it after directed tests pass, and retain the
random seed in failure output. It can be changed at run time:

```python
self.data_agent.set_randomize(True)
self.data_agent.set_packet_logging(True)
```

`set_packet_logging(enable, level=None)` affects packet summaries from the
driver and monitors. `cancel_bfms()` stops the source and monitor background
tasks. `clear_bfms()` clears queued source data and monitor protocol state; it
is useful only as controlled environment cleanup, not as a replacement for
reset. The environment calls `cancel_bfms()` from `stop_tasks()` in a `finally`
block.

## The ordered output contract

`BaseVIPScoreboard` owns a FIFO expectation queue. Every observed output packet
must match the first item in this queue. Packet order and packet type are
always checked. An output packet is an error when the queue is empty.

The base class is a protocol engine, not a DUT predictor. A subclass implements
three hooks:

- `process_input_packet(packet)` maps one input packet to zero or more output
  expectations;
- `process_control_transaction(transaction)` updates DUT state from observed
  control traffic;
- `on_reset()` resets custom protocol context and the behavior model.

The subclass calls `add_expectation()` for every packet that the DUT should
produce. If an input packet should produce no output, it adds nothing.

## Packet expectations and check modes

`PacketExpectation` contains an expected VIP packet and its comparison
contract. `CheckMode` selects how much content is checked.

| Check mode | Control packet | User packet | Video packet |
| --- | --- | --- | --- |
| `EXACT` | geometry and interlaced/progressive state | user type and full payload | decoded frame content |
| `SHAPE` | same checks as `EXACT` | user type and payload length | payload length |

The expected and observed packet types must also be identical. For an exact
video check, `tolerance` sets the allowed sample difference. It does not change
control, user, or shape-only checks.

`SHAPE` is useful when output data is not defined but the DUT must still
produce a packet with the correct type and size. It is an active check, not a
skipped comparison.

## User packet policy

`UserPacketPolicy` describes the common mapping for input user packets.

| Policy | Custom scoreboard action | Result at the output |
| --- | --- | --- |
| `DROP` | add no expectation | any user output is unexpected |
| `PASSTHROUGH` | add an exact expectation for the input packet | type and payload must be unchanged |

`DROP` is the default. The base class stores the policy value but does not
apply it automatically. The custom scoreboard must read the policy and create
the required expectation.

```python
def process_input_user_packet(self, packet):
    if self.user_packet_policy is UserPacketPolicy.PASSTHROUGH:
        self.add_expectation(PacketExpectation(packet))
```

These two policies cover unchanged and removed user packets. If the DUT
transforms a user payload, the custom scoreboard should calculate the new
payload and add an exact `VIPUserPacket` expectation directly.

## Video packet policy

Video behavior can change from one packet to the next because it often depends
on register state, a warm-up period, or frame history. A behavior-model video
operation therefore returns one `VideoPacketResult` for each input video
packet.

| Policy | Required model result | Custom scoreboard action |
| --- | --- | --- |
| `EXACT` | expected frame or payload; optional tolerance | create an exact video expectation |
| `SHAPE` | expected data is optional | create a video reference with the correct output payload length and use `CheckMode.SHAPE` |
| `DROP` | no expected data and zero tolerance | add no expectation |

Use the factory methods to make the contract clear:

```python
VideoPacketResult.exact(expected_frame, tolerance=1)
VideoPacketResult.shape(reason="output content is not defined")
VideoPacketResult.drop(reason="no output during this state")
```

`EXACT` requires an expected value. `DROP` rejects both an expected value and a
non-zero tolerance. `SHAPE` may omit expected data, but the custom scoreboard
must still build a `VIPVideoPacket` reference with the correct output payload
length.

`VideoPacketResult` is the boundary between the behavior model and the custom
scoreboard. `BaseVIPScoreboard` does not consume it directly. The custom
scoreboard converts it to `PacketExpectation`:

```python
def process_input_video_packet(self, packet):
    frame = self.decode_input_frame(packet)  # Custom protocol adapter.
    result = self.behavior_model.process_video_frame(frame)

    if result.policy is VideoPacketPolicy.DROP:
        return

    expected_packet = self.build_video_reference(packet, result)
    self.add_expectation(
        PacketExpectation(
            expected_packet,
            check=CheckMode(result.policy.value),
            reason=result.reason,
            tolerance=result.tolerance,
        )
    )
```

Here `decode_input_frame()` and `build_video_reference()` are custom helpers,
not library methods. They handle the input and output formats of the DUT. For
an exact result, the second helper normally encodes `result.expected`. For a
shape result, it creates a reference packet of the required output length.

Control packets do not use `UserPacketPolicy` or `VideoPacketPolicy`. The
custom scoreboard creates their `PacketExpectation` directly. It can preserve
the input geometry or calculate a new output geometry.

## Connect monitors to the scoreboard

Connect the source monitor, sink monitor, and optional control monitor in the
environment's `connect_phase()`:

```python
def connect_phase(self):
    self.data_agent.source_analysis_port.connect(
        self.scoreboard.data_in_export
    )
    self.data_agent.sink_analysis_port.connect(
        self.scoreboard.data_out_export
    )
    self.control_agent.analysis_port.connect(
        self.scoreboard.control_export
    )
```

The scoreboard needs `source_fmt` to decode input video and `sink_fmt` to
decode output video. `sink_fmt` is always required. For an output-only VIP
path, omit `source_fmt` and add a dedicated analysis export for the physical
source transaction.

A non-VIP `FrameSource` publishes `FrameTransaction` before it drives the
physical conduit. This ordering lets the scoreboard create an expectation
before the DUT can produce output.

## Reset, completion, and failures

When reset is asserted, the base scoreboard:

1. stops accepting input and output packets;
2. clears pending expectations and output geometry;
3. starts a new protocol epoch;
4. calls `on_reset()`.

The custom hook should clear input geometry and reset the behavior model. A
mismatch found before reset remains sticky, so reset cannot hide a failed
check.

Use `wait_frame_checked()` when a test must wait for one more successfully
checked video packet. Use `drain()` at the end of a stimulus group or test.
`drain()` waits until the expectation queue is empty, raises a stored failure,
and can then observe a quiet clock window. Any packet received during that
quiet window is unexpected.

One independent VIP output path should have one `BaseVIPScoreboard`. This keeps
packet order, geometry, failures, and frame counters isolated.

Use the environment lifecycle from [Project style](testbench-style.md):
construct components in `build_phase()`, connect analysis ports in
`connect_phase()`, and stop every background task in a `finally` block.
