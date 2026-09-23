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

Next: [measure stream performance](performance.md).
