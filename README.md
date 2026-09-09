<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5

Unless explicitly acquired and licensed from Licensor under another license,
the contents of this file are subject to the Reciprocal Public License ("RPL")
Version 1.5, or subsequent versions as allowed by the RPL, and You may not copy
or use this file in either source code or executable form, except in compliance
with the terms and conditions of the RPL.

All software distributed under the RPL is provided strictly on an "AS IS"
basis, WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, AND LICENSOR
HEREBY DISCLAIMS ALL SUCH WARRANTIES, INCLUDING WITHOUT LIMITATION, ANY
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, QUIET
ENJOYMENT, OR NON-INFRINGEMENT. See the RPL for specific language governing
rights and limitations under the RPL.
-->

## About

Reusable FPGA verification helpers. The package provides shared data formats,
wire-protocol codecs, cocotb simulation utilities, and an Intel System Console
HIL transport.

### Warning: 
- The project is currently under development
- I try to release stable versions, but there may be bugs :)

## Install

Install the package:

```bash
python -m pip install fpga-verification
```

This installs the numeric format helpers, protocol codecs, cocotb simulation
utilities, pyuvm agents, and Intel System Console HIL helpers together.

## Roadmap

```text
fpga_verification
├── formats                         integer and fixed-point raw words
├── video                           numpy frames and payload packing
├── protocols.avalon_st.intel_video Intel VIP packets and codecs
├── sim
│   ├── agents                      pyuvm agents built on cocotbext.avalon
│   ├── bfms                        Intel DMA model
│   ├── models / scoreboards        prediction and output checking
│   ├── stream_metrics              latency and throughput analysis
│   └── runners / platform_designer simulation launch helpers
└── hil.intel                       Quartus System Console access

cocotbext.avalon                    external Avalon-ST and Avalon-MM BFMs
```

Start with the [library overview](examples/00_library_overview.ipynb), then
follow the path that matches the verification task:

- Numeric and video data: [numeric formats](examples/01_numeric_formats.ipynb)
  → [video frames](examples/02_video_frames.ipynb).
- Streaming simulation: [Avalon-ST](examples/03_avalon_st_bus.ipynb) →
  [Intel VIP packets](examples/05_intel_vip_packets_and_agent.ipynb) →
  [VIP verification components](examples/09_vip_verification_components.ipynb)
  → [performance metrics](examples/10_stream_performance_metrics.ipynb).
- Register and memory interfaces:
  [Avalon-MM](examples/04_avalon_mm_bus.ipynb) and
  [Intel DMA](examples/06_intel_dma_bfm.ipynb).
- Tools and hardware:
  [System Console HIL](examples/07_hil_system_console.ipynb) and
  [simulation runners](examples/08_simulation_runners.ipynb).

The notebooks state whether they run in plain Python or require cocotb,
Quartus, a supported simulator, or connected hardware.

## Public API

```python
from fpga_verification.formats import QFormat, UIntFormat
from fpga_verification.protocols.avalon_st.intel_video import (
    IntelVIPFrameCodec,
    VIPControlPacket,
    VIPFrame,
    VIPInterlacing,
    VIPPacketType,
    VIPProtocolChecker,
    VIPProtocolError,
    VIPUserPacket,
    VIPVideoPacket,
    vip_packet_from_symbols,
)
from cocotbext.avalon import (
    AvalonFormat,
    AvalonMMBus,
    AvalonMMMasterBFM,
    AvalonMMMemoryBFM,
    AvalonMMSlaveBFM,
    AvalonMMTransaction,
    AvalonSTBeat,
    AvalonSTBus,
    AvalonSTFrame,
    AvalonSTMonitor,
    AvalonSTSink,
    AvalonSTSource,
)
from fpga_verification.sim.bfms.intel_dma import (
    DMAAddressRegion,
    IntelDMABFM,
    IntelDMACommandMonitor,
    SparseByteMemory,
)
from fpga_verification.sim.agents import (
    AvalonMMAgent,
    AvalonMMMonitor,
    VIPAgent,
    VIPItem,
    VIPMonitor,
    VIPSequence,
)
from fpga_verification.sim.models import BaseVIPPredictor, PacketExpectation
from fpga_verification.sim.scoreboards import AnalysisImp, BaseVIPScoreboard
from fpga_verification.sim import (
    PacketMetrics,
    PacketObservation,
    PacketSequenceMetrics,
    StreamPerformanceAnalyzer,
)
from fpga_verification.sim.platform_designer import platform_test_cocotb
from fpga_verification.sim.runners import (
    intel_component_test_cocotb,
    rtl_test_cocotb,
    run_intel_component_test,
    run_rtl_test,
)
from fpga_verification.hil.intel import IntelSystemConsoleSession
```

## Numeric Formats

`UIntFormat` and `QFormat` convert between Python/numpy values and raw integer
words used by hardware buses, memories, and scoreboards.

### UIntFormat

```python
from fpga_verification.formats import UIntFormat

pixel = UIntFormat(width=10)
raw_pixels = pixel.array([0, 1023, 1024, -1])

assert raw_pixels.tolist() == [0, 1023, 0, 1023]
assert raw_pixels.dtype == pixel.dtype
```

Inputs:

- `width`: unsigned word width in bits, from 1 to 64.
- `zeros(shape)`: creates a zero-filled numpy array.
- `wrap(values)`: masks values to the configured width.
- `array(values, shape=None)`: masks, casts to the smallest unsigned storage
  dtype, and optionally reshapes.

Outputs:

- `dtype`: numpy unsigned dtype selected from `uint8`, `uint16`, `uint32`, or
  `uint64`.
- `mask`: integer bit mask for the configured width.

### QFormat

```python
from fpga_verification.formats import QFormat

sample = QFormat(qi=3, qf=2, signed=True)
raw = sample.float_to_qraw([1.25, -1.0])
back = sample.qraw_to_float(raw)

assert raw.tolist() == [5, 28]
assert back.tolist() == [1.25, -1.0]
```

Inputs:

- `qi`: integer width. For signed formats, this includes the sign bit.
- `qf`: fractional width.
- `signed`: `True` for two's-complement signed values, `False` for unsigned.
- `float_to_qraw(x, saturate=True)`: converts floats to raw fixed-point words.
- `int_to_qraw(raw, saturate=True)`: converts signed integer values to raw
  stored words.
- `qraw_to_int(raw)`: converts raw words to signed or unsigned integers.
- `qraw_to_float(raw)`: converts raw words to floating-point values.
- `multiply(left_raw, right_format, right_raw, out_qf=None)`: multiplies two
  raw fixed-point arrays. If `out_qf` is provided, the result is shifted to the
  requested fractional width.
- `zeros(size=None)`, `ones(size=None)`, `full(size, value, raw=False)`, and
  `randomize(...)`: create test data.

Outputs:

- `width`: total raw word width, `qi + qf`.
- `scale`: `2 ** qf`.
- `mask`: integer bit mask for the raw word.
- `min_float`, `max_float`: representable numeric range.
- `dtype`: numpy unsigned storage dtype for the raw word.

## Video frames

The neutral video layer is independent of cocotb and protocol-specific packet
formats:

```python
from fpga_verification.video import (
    FrameSize,
    ImageGenerator,
    VideoFormat,
    VideoPayloadCodec,
    compare_frames,
)

fmt = VideoFormat(
    bits_per_symbol=10,
    number_of_color_planes=3,
    color_planes_are_in_parallel=True,
    pixels_in_parallel=2,
)
size = FrameSize(width=640, height=480)
generator = ImageGenerator(fmt, rng=1)
frame = generator.random(size)

codec = VideoPayloadCodec(fmt)
payload_beats = codec.pack_frame(frame, size)
decoded = codec.unpack_frame(payload_beats, size)
compare_frames(decoded, frame)
```

`VideoFormat` contains only static AV-ST sample layout. `FrameSize` contains
the width and height of one frame and is an explicit argument to every
generation and conversion operation. One codec can therefore process frames
with different resolutions without retaining hidden state.

Canonical frame shapes are `(height, width)` for one color plane and
`(height, width, planes)` for multiple planes. Sample zero occupies the least
significant payload bits. In parallel-plane mode each pixel's planes are
adjacent; in serial-plane mode each beat carries one plane for
`pixels_in_parallel` adjacent pixels.

Row-oriented adapters (`row_to_symbols`, `pack_row`, `pack_frame`) pad each
incomplete row to the configured interface beat width and validate that padding
on decode. Frame-symbol adapters (`frame_to_symbols`, `symbols_to_frame`) use a
continuous raster stream with no per-row padding; protocols such as Intel VIP
carry any final partial beat with Avalon-ST `empty`.

`ImageGenerator` provides `constant`, `linspace`, `random`, and
`horizontal_ramp`. `VideoPayloadCodec` provides frame/row/symbol/beat
round-trips and strict shape, range, payload-length, and padding validation.

## Avalon-ST Protocols

Avalon-ST helpers follow the Avalon interface terminology used by Intel/Altera.
The protocol reference is:
https://docs.altera.com/r/docs/683091/22.3/avalon-interface-specifications/introduction-to-the-avalon-interface-specifications

The protocol codec layer is independent of cocotb and simulator state. It
accepts and returns Python lists of symbols.

### Intel Avalon-ST Video Packets

```python
from fpga_verification.protocols.avalon_st.intel_video import (
    VIPControlPacket,
    VIPFrame,
    VIPInterlacing,
    VIPUserPacket,
    vip_packet_from_symbols,
)

control = VIPControlPacket(
    width=1920,
    height=1080,
    interlacing=VIPInterlacing.PROGRESSIVE_FRAME,
)
symbols = control.to_symbols()
decoded = vip_packet_from_symbols(symbols)

assert decoded.width == 1920
assert decoded.height == 1080

frame = VIPFrame(
    width=2,
    height=2,
    pixels=[0x10, 0x20, 0x30, 0x40],
    user_packets=[VIPUserPacket(1, [0xA, 0xB])],
)
packets = frame.packets()
```

Inputs:

- `VIPControlPacket(width, height, interlacing=...)`: frame dimensions and
  interlacing metadata. Width and height must fit in 16 bits.
- `VIPVideoPacket(payload)`: video payload symbols.
- `VIPUserPacket(user_type, payload)`: user packet type `1..8` and payload
  symbols.
- `VIPFrame(width, height, pixels, interlacing=..., user_packets=...)`: a
  black-box container that produces user, control, and video packets.
- `vip_packet_from_symbols(symbols, symbols_per_beat=1)`: decodes one packet
  from raw symbols. `symbols_per_beat` controls how many symbols belong to the
  first Avalon-ST beat; payload starts after that first beat.

Outputs:

- `to_symbols()`: returns a list of 4-bit packet symbols.
- `VIPFrame.control_packet()`: returns a `VIPControlPacket`.
- `VIPFrame.video_packet()`: returns a `VIPVideoPacket`.
- `VIPFrame.packets()`: returns user packets followed by control and video
  packets.
- `VIPInterlacing.description`: human-readable interlacing mode.

Ancillary packets are currently reported as unsupported by the decoder.

### VIP Protocol Checker

`VIPProtocolChecker` validates the packet order and active frame size for one
observed Intel VIP stream. The codec stays stateless; the checker owns the
stream state:

```python
from fpga_verification.protocols.avalon_st.intel_video import VIPProtocolChecker

checker = VIPProtocolChecker(fmt)

for packet in observed_packets:
    checker.observe(packet)
```

The checker enforces these wire-visible rules:

- a video packet must follow a control packet;
- a reset clears the active control resolution when used through `VIPMonitor`.

It can also validate video payload length against the most recent control
packet resolution and `VideoFormat`. In the current default mode a mismatch is
logged as a warning; set `checker.check_video_packet_size = True` to raise
`VIPProtocolError` instead.

Equal-area frame-size changes cannot be detected by a passive stream checker,
because Intel VIP video packets do not carry width or height.

### VIP pyuvm Agent

`VIPAgent` wraps Intel VIP source, monitor, sink, sequencer, and driver pieces
for pyuvm environments. When a bus is provided, the corresponding monitor is
created automatically and publishes decoded `VIPPacket` objects through its
analysis port. Each monitor also runs `VIPProtocolChecker` before publishing.

```python
from fpga_verification.sim.agents import VIPAgent, VIPSequence

vip_agent = VIPAgent(
    "vip_agent",
    parent=self,
    clock=dut.clk,
    reset=dut.reset,
    source_bus=din_bus,
    sink_bus=dout_bus,
    source_fmt=fmt,
    sink_fmt=fmt,
    packet_logging=True,
)

packets = codec.frame_to_packets(frame, size)
sequence = VIPSequence.from_packets(packets, name="input_frame")
await sequence.start(vip_agent.sequencer)
```

Inputs:

- `source_bus` and `source_fmt`: stream driven by the active agent and observed
  by `source_monitor`.
- `sink_bus` and `sink_fmt`: stream observed by `sink_monitor`; in active mode
  the sink monitor also drives ready/backpressure.
- `is_active`: active agents create a sequencer and source driver when
  `source_bus` is present. Passive agents only monitor provided buses.
- `packet_logging` and `packet_log_level`: optional packet summaries such as
  `nuc_component.dout: got vip video packet (2048 symbols)`.
- `set_packet_logging(enable, level=None)`: updates logging after build.
- `randomize`: enables randomized source pauses and sink backpressure.

Outputs:

- `source_monitor.analysis_port`: decoded packets observed on `source_bus`.
- `sink_monitor.analysis_port`: decoded packets observed on `sink_bus`.
- `sequencer`: accepts `VIPSequence` items in active source mode.

### Base VIP Predictor And Scoreboard

`BaseVIPPredictor` and `BaseVIPScoreboard` split Intel VIP checking into two
parts. The predictor consumes input packets and produces expected output packet
descriptions. The scoreboard receives both DUT input and output packet streams,
queues predictor expectations, and compares observed output packets against
those expectations. The input stream and predictor are optional, so the same
scoreboard also supports output-only IP paths with explicit expectations.

Packet-flow diagram:

![packet processing](src/fpga_verification/sim/scoreboards/docs/scoreboard.jpg)

```python
from fpga_verification.sim.models import BaseVIPPredictor, PacketExpectation
from fpga_verification.sim.scoreboards import BaseVIPScoreboard


class MyVIPPredictor(BaseVIPPredictor):
    def get_tolerance(self):
        return 1


scoreboard = BaseVIPScoreboard(
    "vip_scoreboard",
    self,
    source_fmt=source_fmt,
    sink_fmt=sink_fmt,
)
scoreboard.predictor = MyVIPPredictor(
    model=model,
    input_codec=scoreboard.vip_input_codec,
    output_codec=scoreboard.vip_output_codec,
)

vip_agent.source_monitor.analysis_port.connect(scoreboard.data_in_export)
vip_agent.sink_monitor.analysis_port.connect(scoreboard.data_out_export)
```

An output-only IP can queue expectations explicitly instead of using a
predictor:

```python
scoreboard = BaseVIPScoreboard(
    "output_scoreboard",
    self,
    sink_fmt=output_fmt,
)
vip_agent.sink_monitor.analysis_port.connect(scoreboard.data_out_export)

scoreboard.add_expectation(PacketExpectation(packet=expected_control))
scoreboard.add_expectation(PacketExpectation(packet=expected_video))
```

Predictor behavior:

- `process_packet(packet)`: dispatches input control, video, and user packets.
- Control packets update the active input `FrameSize` and emit an expected
  output control packet using `expected_output_size(input_size)`.
- Video packets are decoded to neutral frames, passed to `process_frame(frame,
  size)`, and encoded back to expected output video packets.
- `support_passthrough=True` allows `set_mode(BaseVIPPredictor.IpMode.PASSTHROUGH)`,
  where input frames are expected unchanged.
- Override `expected_output_size(input_size)`, `is_supported_frame_size(size)`,
  `get_tolerance()`, `process_frame(frame, size)`, or `_process_user_packet()`
  for IP-specific behavior.

Scoreboard behavior:

- `sink_fmt` is required; `source_fmt` is optional.
- `data_in_export`: connect packets observed before the DUT; it is `None` when
  `source_fmt` is omitted.
- `data_out_export`: connect packets observed after the DUT.
- When a predictor is assigned, its output expectations are queued and compared
  with DUT output packets as before.
- `add_expectation(PacketExpectation(...))` lets a test-specific scoreboard
  queue expectations without a predictor. Output packets are compared with
  queued expectations in order.
- Every output packet must match the next queued expectation. An unexpected
  packet or a malformed comparable video packet fails the scoreboard.
- `PacketExpectation(compare=False)` accepts exactly one intentionally
  unchecked video packet. The packet still completes `wait_frame_checked()`,
  so tests do not need to know predictor details such as model warm-up.
- `expected_queue`: stores predictor-generated or explicit expectations until
  matching output packets arrive.
- Control packets compare width, height, and interlacing.
- Video packets compare decoded frames with `compare_frames()` using the
  expectation tolerance.
- `output_frames_cnt` counts compared and explicitly skipped output frames.
- `get_frame_count()` returns the counter used by `wait_frame_checked()`.
- `wait_frame_checked()` waits for one more processed output frame. Its optional
  `after=` value should come from `get_frame_count()` when a test needs an
  explicit checkpoint.

One `BaseVIPScoreboard` instance represents one independent VIP path. For IPs
with multiple inputs or outputs, create one instance per independently checked
path so that active control sizes, expectation queues, failures, and frame
counters remain isolated. An IP-specific parent scoreboard can own those path
scoreboards and route additional inputs to its predictors.

`AnalysisImp` is a small reusable pyuvm helper used by scoreboards when an
analysis export should forward every `write(item)` call to a Python callable:

```python
from fpga_verification.sim.scoreboards import AnalysisImp

self.input_export = AnalysisImp("input_export", self, self.process_input)
```

## Avalon-ST Cocotb Bus Helpers

The cocotb bus helpers drive and observe Avalon-ST interfaces through cocotb
handles. They support scalar `valid`/`ready`, optional packet signals, optional
`empty`, `error`, and `channel`, and ready modes `ready_latency=0` or
`ready_latency=1`.

### Instantiating A Source And Sink

```python
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from cocotbext.avalon import (
    AvalonFormat,
    AvalonSTBus,
    AvalonSTFrame,
    AvalonSTSink,
    AvalonSTSource,
)


@cocotb.test()
async def stream_loopback_test(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    dut.reset.value = 1
    await RisingEdge(dut.clk)
    dut.reset.value = 0

    fmt = AvalonFormat(bits_per_symbol=8, symbols_per_beat=1)

    source = AvalonSTSource(
        AvalonSTBus.from_prefix(dut, "sink"),
        fmt,
        dut.clk,
        reset=dut.reset,
        packets=True,
    )
    sink = AvalonSTSink(
        AvalonSTBus.from_prefix(dut, "source"),
        fmt,
        dut.clk,
        reset=dut.reset,
        packets=True,
    )

    await source.send(AvalonSTFrame([0x11, 0x22, 0x33]))
    received = await sink.recv()

    assert received.data == [0x11, 0x22, 0x33]
```

Inputs:

- `AvalonSTBus.from_prefix(dut, prefix)`: binds signals named like
  `<prefix>_data`, `<prefix>_valid`, `<prefix>_ready`,
  `<prefix>_startofpacket`, and `<prefix>_endofpacket`.
- `AvalonSTFrame(data, channel=None, error=None, empty=None, tx_complete=None)`:
  frame payload and optional sideband metadata.
- `AvalonFormat(bits_per_symbol=8, symbols_per_beat=1,
  first_symbol_in_high_order_bits=False)`: static symbol layout for the
  stream data word.
- `AvalonSTSource(bus, fmt, clock, reset=None, reset_active_level=True,
  ready_latency=0, ready_allowance=None, packets=None, idle_value="x")`.
- `AvalonSTSink(...)` and `AvalonSTMonitor(...)`: use the same `AvalonFormat`
  and timing options as `AvalonSTSource`.
- `send(frame)` / `send_nowait(frame)`: queue transmit data.
- `recv()` / `recv_nowait()`: receive complete frames.
- `recv_beat()` / `recv_beat_nowait()`: receive one transferred beat.
- `set_pause_generator(generator)`: apply backpressure or idle insertion from
  an iterable of booleans.

Outputs:

- `AvalonSTFrame.data`: list of symbols.
- `AvalonSTFrame.channel`, `error`, `empty`: captured sideband metadata.
- `AvalonSTFrame.sim_time_start`, `sim_time_end`: simulation timestamps.
- `AvalonSTBeat`: one handshake beat with `data`, decoded `symbols`, `sop`,
  `eop`, `empty`, `error`, `channel`, and `sim_time`.
- `wait()`: waits for a source to become idle or a monitor/sink to see
  activity, depending on the helper type.

### Stream Performance Metrics

`StreamPerformanceAnalyzer` calculates packet latency, stream efficiency,
packet-boundary gaps, and the clock multiplier required to match an ideal
one-beat-per-cycle stream. It operates on frames captured by Avalon-ST monitors
and is independent of Intel VIP packet type, payload contents, and stream data
width.

The analyzer measures the simulation clock period once from two adjacent
rising edges. Start that calibration concurrently with reset so it adds no
cycles to the useful test scenario:

```python
import cocotb
from cocotb.triggers import ClockCycles

from fpga_verification.sim import (
    PacketObservation,
    StreamPerformanceAnalyzer,
)


analyzer_task = cocotb.start_soon(
    StreamPerformanceAnalyzer.from_clock(dut.clk)
)
await ClockCycles(dut.clk, 4)
analyzer = await analyzer_task

observations = [
    PacketObservation(
        name="video[0]",
        beats=video_0_beats,
        input_frame=observed_input_0,
        output_frame=observed_output_0,
    ),
    PacketObservation(
        name="video[1]",
        beats=video_1_beats,
        input_frame=observed_input_1,
        output_frame=observed_output_1,
    ),
]

sequence = analyzer.sequence("back-to-back video", observations)
sequence.log(dut._log)

sequence.assert_input_packet_gap_at_most(0)
sequence.assert_all_boundaries_overlap()

clock_multiplier = sequence.required_clock_multiplier
```

For one packet, `analyzer.packet(observation)` returns:

- input and output packet spans in cycles;
- input efficiency and stall cycles;
- output efficiency and bubble cycles;
- SoP latency, EoP latency, and complete end-to-end latency.

For an ordered packet sequence, `analyzer.sequence(...)` additionally returns:

- `input_packet_gaps` and `output_packet_gaps`: idle cycles between accepted
  EoP and the next accepted SoP;
- input and output SoP-to-SoP intervals;
- `boundary_overlaps`: whether the next packet entered before the previous
  packet completed at the output;
- `max_packets_in_flight`;
- sequence input/output efficiency;
- `sustainable_efficiency`, the lower of input and output efficiency;
- `required_clock_multiplier`, calculated as
  `1 / sustainable_efficiency`.

For example, an efficiency of `0.83` produces a clock multiplier of
approximately `1.205`. The library intentionally reports only this
dimensionless coefficient; conversion to a target clock frequency belongs to
the test or system-level calculation.

To measure DUT throughput rather than testbench behavior:

- queue the complete packet sequence before transmission starts;
- keep the output sink continuously ready;
- use a sufficiently long and representative packet sequence;
- measure input and output streams in one stable clock domain.

`from_clock()` only samples two edges during initialization. It does not start
a permanent clock-counting coroutine and does not change the Avalon-ST monitor
hot path. A clock whose period changes during the measured sequence requires a
different cycle-counting strategy.


## Avalon-MM Cocotb Bus Helpers

`AvalonMMMasterBFM` is a lightweight Avalon-MM host BFM for register-style
cocotb tests. It issues one transaction at a time and is intentionally simpler
than the full Avalon-MM protocol surface.

```python
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from cocotbext.avalon import AvalonMMMasterBFM


@cocotb.test()
async def control_register_test(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mm = AvalonMMMasterBFM.from_prefix(
        dut,
        "control",
        dut.clk,
        reset=dut.reset,
        default_byteenable=0xF,
    )
    mm.start()

    dut.reset.value = 1
    await RisingEdge(dut.clk)
    dut.reset.value = 0
    await mm.wait_reset_release(active_value=1)

    await mm.write(0x00, 0x00000001, timeout_cycles=32)
    status = await mm.read(0x04, timeout_cycles=32)
    await mm.wait_set(0x04, 0x1, timeout_cycles=256)
```

For pyuvm environments, `AvalonMMMonitor` passively observes accepted read and
write requests and publishes `AvalonMMTransaction` objects. `AvalonMMAgent`
always creates this monitor and can also create an active `AvalonMMMasterBFM`.

```python
from pyuvm import uvm_active_passive_enum, uvm_env

from fpga_verification.sim.agents import AvalonMMAgent
from cocotbext.avalon import AvalonMMBus


class MyEnv(uvm_env):
    def build_phase(self):
        self.control_agent = AvalonMMAgent(
            "control_agent",
            self,
            bus=AvalonMMBus.from_prefix(dut, "control"),
            clock=dut.clk,
            reset=dut.reset,
            is_active=uvm_active_passive_enum.UVM_ACTIVE,
            default_byteenable=0xF,
            packet_logging=True,
        )

    def connect_phase(self):
        self.control_agent.analysis_port.connect(self.scoreboard.mm_export)
```

An active agent exposes its host BFM as `agent.master`:

```python
await env.control_agent.master.write(0x00, 0x1, timeout_cycles=32)
status = await env.control_agent.master.read(0x04, timeout_cycles=32)
```

`AvalonMMMemoryBFM` is a slave-side BFM for full-IP tests where the DUT exposes
Avalon-MM master ports. It can connect read-only, write-only, or read/write
master ports to any byte-addressed memory object with `read(address, length)`
and `write(address, data)` methods, including `SparseByteMemory`.

```python
from cocotbext.avalon import AvalonMMMemoryBFM
from fpga_verification.sim.bfms.intel_dma import SparseByteMemory


memory = SparseByteMemory()
memory.write(0x1000, b"\x01\x02\x03\x04")

rd_mem = AvalonMMMemoryBFM.from_prefix(
    dut,
    "mem_master_rd",
    dut.mem_clk,
    reset=dut.mem_reset,
    memory=memory,
).start()

wr_mem = AvalonMMMemoryBFM.from_prefix(
    dut,
    "mem_master_wr",
    dut.mem_clk,
    reset=dut.mem_reset,
    memory=memory,
).start()
```

Inputs:

- `AvalonMMBus.from_prefix(dut, prefix)`: binds required `<prefix>_address`
  plus optional `<prefix>_writedata`, `<prefix>_write`, `<prefix>_read`,
  `<prefix>_readdata`, `<prefix>_waitrequest`, `<prefix>_readdatavalid`,
  `<prefix>_byteenable`, `<prefix>_burstcount`,
  `<prefix>_beginbursttransfer`, `<prefix>_response`,
  `<prefix>_writeresponsevalid`, `<prefix>_lock`, and
  `<prefix>_debugaccess`.
- `AvalonMMMasterBFM(bus, clock, reset=None, read_response_latency=0,
  default_byteenable=None, packet_logging=False, packet_log_level=logging.INFO)`:
  creates a single-beat Avalon-MM host.
- `AvalonMMMonitor(name, parent, bus, clock, reset=None,
  reset_active_level=True, packet_logging=False,
  packet_log_level=logging.INFO)`: observes accepted read/write requests and
  publishes `AvalonMMTransaction` objects through `analysis_port`.
- `AvalonMMAgent(name, parent, bus, clock, reset=None,
  reset_active_level=True, is_active=UVM_PASSIVE, packet_logging=False,
  packet_log_level=logging.INFO, read_response_latency=0,
  default_byteenable=None)`: creates an always-on monitor and, in active mode,
  a `master` BFM for register access. Packet logging is routed to the monitor
  in passive mode and to the master in active mode.
- `AvalonMMMemoryBFM(bus, clock, reset=None, memory=..., read_latency=1,
  byteorder="little")`: creates a slave-side byte-addressed memory BFM.
- `start()`: drives master outputs to idle values.
- `write(address, data, byteenable=None, timeout_cycles=None)`: issues one
  write and waits until `waitrequest` is deasserted, when present.
- `read(address, byteenable=None, timeout_cycles=None)`: issues one read and
  waits for `readdatavalid` when present, otherwise waits the configured fixed
  `read_response_latency`.
- `read_modify_write(address, update, ...)`: convenience read/update/write.
- `poll(address, predicate, ...)`, `wait_set(address, mask, ...)`, and
  `wait_clear(address, mask, ...)`: register polling helpers.
- `AvalonMMTransaction(kind, address, data, byteenable, burstcount,
  beat_index)`: transaction object emitted by the monitor and memory-side
  recorder.
- `AvalonMMMemoryBFM.read_transactions` and `write_transactions`: observed
  memory-side transfer beats.

Supported Avalon-MM features:

- Master BFM: single-beat read and write transfers for register access.
- Monitor/agent: passive observation of accepted single-beat Avalon-MM
  read/write requests, including `address`, optional write `data`,
  `byteenable`, and `burstcount`.
- Memory BFM: read and write bursts via `burstcount`.
- Optional `waitrequest` backpressure.
- Optional `readdatavalid` variable-latency read completion.
- Optional fixed read response latency when `readdatavalid` is absent.
- Optional `byteenable`, defaulting to all byte lanes asserted when present.
- Separate read-only and write-only master ports sharing one backing memory.
- Intel mSGDMA-style write bursts where `address` and `burstcount` remain
  constant while each accepted write beat advances the memory address.
- Width validation for address, data, and byteenable values.

Unsupported features:

- Master BFM burst generation.
- Out-of-order read responses.
- Read/write response status behavior beyond idle driving of optional
  `response` and `writeresponsevalid`.
- `waitrequestAllowance`, active-low role variants, reset-interface timing, and
  Platform Designer address-unit/alignment property modeling.

Reference: https://docs.altera.com/r/docs/683091/current

## Intel DMA BFM

`IntelDMABFM` is a cocotb black-box model for Intel read and write DMA streaming
interfaces. It consumes DMA command descriptors, emits DMA responses, sources
read data from memory, and stores write data into memory.

```python
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from cocotbext.avalon import AvalonSTBus
from fpga_verification.sim.bfms.intel_dma import (
    DMAAddressRegion,
    IntelDMABFM,
    IntelDMACommandMonitor,
    SparseByteMemory,
)


@cocotb.test()
async def dma_component_test(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    memory = SparseByteMemory()
    memory.write(0x1000, b"\x01\x02\x03\x04")

    dma = IntelDMABFM(
        dut,
        clock=dut.clk,
        reset=dut.reset,
        memory=memory,
        mode="full",
    ).start()

    command_monitor = IntelDMACommandMonitor(
        clock=dut.clk,
        reset=dut.reset,
        rdma_cmd_bus=AvalonSTBus.from_prefix(dut, "rdma_cmd"),
        wdma_cmd_bus=AvalonSTBus.from_prefix(dut, "wdma_cmd"),
        read_address_regions=[DMAAddressRegion("input", 0x1000, 0x4000)],
        write_address_regions=[DMAAddressRegion("output", 0x8000, 0x4000)],
    ).start()

    dut.reset.value = 1
    await RisingEdge(dut.clk)
    dut.reset.value = 0

    # Drive the DUT here. The BFM responds on the DMA Avalon-ST interfaces.
    # Later, inspect memory or descriptor logs as black-box outputs.
    written_bytes = memory.read(0x8000, 16)
    read_descriptors = command_monitor.read_descriptors

    dma.stop()
    command_monitor.stop()
```

Inputs:

- `IntelDMABFM(dut, clock, reset, memory=None, read_response_delay_cycles=2,
  write_response_delay_cycles=2, ..., mode="full")`.
- `mode`: `"full"`, `"read"`/`"read_only"`, or `"write"`/`"write_only"`.
- `memory`: optional `SparseByteMemory` shared by read and write paths.
- Optional bus overrides: `rdma_cmd_bus`, `rdma_resp_bus`, `wdma_cmd_bus`,
  `wdma_resp_bus`, `din_bus`, and `dout_bus`. If omitted, buses are discovered
  from DUT prefixes with the same names.
- `SparseByteMemory.write(address, data)`: initializes byte-addressed memory.
- `DMAAddressRegion(name, start, size)`: allowed address interval for passive
  checking. End address is exclusive.
- `IntelDMACommandMonitor(...)`: pass command buses or existing
  `AvalonSTMonitor` instances and optional allowed address regions.

Outputs:

- `SparseByteMemory.read(address, length)`: returns bytes stored by the BFM.
- `IntelDMABFM.read_commands`, `write_commands`: descriptor queues observed by
  the model.
- `IntelDMABFM.read_responses`, `write_responses`: queues of descriptors whose
  responses were issued.
- `IntelDMACommandMonitor.read_descriptors`, `write_descriptors`: decoded
  descriptor history.
- `ReadDMADescriptor.decode(value)` and `WriteDMADescriptor.decode(value)`:
  convert raw descriptor words into address, length, and control fields.

## HIL Session

`IntelSystemConsoleSession` opens one persistent `system-console` process and
uses it sequentially for Avalon-MM memory access and JTAG UART commands. Intel
Quartus `system-console` must be available on `PATH`.

```python
import numpy as np

from fpga_verification.hil.intel import IntelSystemConsoleSession

frame = np.arange(1024 * 1280, dtype=np.uint16).reshape(1024, 1280)

with IntelSystemConsoleSession(
    system_console="system-console",
    master_index=0,
    uart_index=0,
    startup_timeout=30.0,
    work_dir=".",
) as hw:
    hw.write_memory(frame, address=0x01E84800)
    response = hw.command("g\n", timeout=3.0)
    frame_out = hw.read_memory((1024, 1280), address=0x02DC6C00)

print(response)
print(frame_out.shape)
```

Inputs:

- `system_console`: executable name or path.
- `master_index`: System Console Avalon-MM master index.
- `uart_index`: JTAG UART service index.
- `startup_timeout`: seconds to wait for the Tcl worker to become ready.
- `work_dir`: directory used for temporary binary transfer files.
- `write_memory(data, address, chunk_size=4096)`: writes numpy-compatible data
  as little-endian 16-bit words.
- `read_memory(shape, address, chunk_size=4096)`: reads little-endian 16-bit
  words and reshapes them.
- `command(command, timeout=3.0, debug=False)`: sends a UTF-8 command over JTAG
  UART and waits for the first non-empty response line.

Outputs:

- `read_memory(...)`: numpy array with the requested shape.
- `command(...)`: response string.
- Methods raise `TimeoutError` or `RuntimeError` if System Console stops or
  reports a protocol error.

## Simulation Runners

See [runners documentation](./docs/sim/runners.md).