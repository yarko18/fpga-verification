# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""
Minimal Avalon-ST cocotb helpers in cocotbext-axi style.

Supports:
  - AvalonSTFrame
  - AvalonSTBeat
  - AvalonSTBus.from_prefix(...)
  - AvalonSTSource.send(...)
  - AvalonSTSink.recv(...)
  - AvalonSTSink.recv_beat(...)
  - pause / set_pause_generator(...)
  - packets=True / False / None(auto)

Supported ready modes:
  - ready_latency=0, ready_allowance=0
  - ready_latency=1, ready_allowance=1

Not supported yet:
  - ready_allowance > ready_latency
  - ready_latency > 1
"""

import logging
import random
from numbers import Integral

import cocotb
from cocotb.queue import Queue, QueueFull
from cocotb.triggers import RisingEdge, Timer, First, Event, ReadOnly, ValueChange, Edge
from cocotb.utils import get_sim_time
from cocotb_bus.bus import Bus
from cocotb.handle import Immediate

try:
    from cocotb.types import LogicArray
except ImportError:
    LogicArray = None

class AvalonFormat:
    """Static symbol layout of an Avalon-ST data interface."""

    def __init__(
        self,
        bits_per_symbol=8,
        symbols_per_beat=1,
        first_symbol_in_high_order_bits=False,
    ):
        self.bits_per_symbol = self._require_positive_int(
            "bits_per_symbol",
            bits_per_symbol,
        )
        self.symbols_per_beat = self._require_positive_int(
            "symbols_per_beat",
            symbols_per_beat,
        )
        self.first_symbol_in_high_order_bits = bool(first_symbol_in_high_order_bits)

    @staticmethod
    def _require_positive_int(name, value):
        if not isinstance(value, Integral):
            raise TypeError(f"{name} must be an integer")
        value = int(value)
        if value <= 0:
            raise ValueError(f"{name} must be > 0, got {value}")
        return value

    @property
    def payload_width(self):
        return int(self.bits_per_symbol) * int(self.symbols_per_beat)


class AvalonSTFrame:
    def __init__(
        self,
        data=None,
        channel=None,
        error=None,
        empty=None,
        tx_complete=None,
    ):
        self.data = []
        self.channel = None
        self.error = None
        self.empty = None
        self.sim_time_start = None
        self.sim_time_end = None
        self.tx_complete = None

        if data is None:
            self.data = []
        elif type(data) is AvalonSTFrame:
            self.data = list(data.data)
            self.channel = data.channel
            self.error = data.error
            self.empty = data.empty
            self.sim_time_start = data.sim_time_start
            self.sim_time_end = data.sim_time_end
            self.tx_complete = data.tx_complete
        elif type(data) in (bytes, bytearray):
            self.data = list(data)
        else:
            self.data = list(data)

        if channel is not None:
            self.channel = channel
        if error is not None:
            self.error = error
        if empty is not None:
            self.empty = empty
        if tx_complete is not None:
            self.tx_complete = tx_complete

    def handle_tx_complete(self):
        if isinstance(self.tx_complete, Event):
            self.tx_complete.set(self)
        elif callable(self.tx_complete):
            self.tx_complete(self)

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def __bytes__(self):
        return bytes(self.data)

    def __eq__(self, other):
        if not isinstance(other, AvalonSTFrame):
            return False

        return (
            self.data == other.data
            and self.channel == other.channel
            and self.error == other.error
            and self.empty == other.empty
        )

    def __repr__(self):
        data_hex = "[" + ", ".join(hex(x) for x in self.data) + "]"
        return (
            f"{type(self).__name__}(data={data_hex}, "
            f"channel={self.channel!r}, "
            f"error={self.error!r}, "
            f"empty={self.empty!r}, "
            f"size={self.__len__()!r}, "
            f"sim_time_start={self.sim_time_start!r}, "
            f"sim_time_end={self.sim_time_end!r})"
        )


class AvalonSTBeat:
    def __init__(
        self,
        data=0,
        symbols=None,
        sop=0,
        eop=0,
        empty=0,
        error=0,
        channel=0,
        sim_time=None,
    ):
        self.data = data
        self.symbols = list(symbols) if symbols is not None else []
        self.sop = sop
        self.eop = eop
        self.empty = empty
        self.error = error
        self.channel = channel
        self.sim_time = sim_time

    def __repr__(self):
        symbols_hex = "[" + ", ".join(hex(x) for x in self.symbols) + "]"
        return (
            f"{type(self).__name__}(data={hex(self.data)}, "
            f"symbols={symbols_hex}, "
            f"sop={self.sop!r}, "
            f"eop={self.eop!r}, "
            f"empty={self.empty!r}, "
            f"error={self.error!r}, "
            f"channel={self.channel!r}, "
            f"sim_time={self.sim_time!r})"
        )


class AvalonSTBus(Bus):
    _signals = ["data"]
    _optional_signals = [
        "valid",
        "ready",
        "startofpacket",
        "endofpacket",
        "empty",
        "error",
        "channel",
    ]

    def __init__(self, entity=None, prefix=None, **kwargs):
        super().__init__(
            entity,
            prefix,
            self._signals,
            optional_signals=self._optional_signals,
            **kwargs,
        )

    @classmethod
    def from_entity(cls, entity, **kwargs):
        return cls(entity, **kwargs)

    @classmethod
    def from_prefix(cls, entity, prefix, **kwargs):
        return cls(entity, prefix, **kwargs)


class AvalonSTBase:
    _type = "base"

    _init_x = False
    _valid_init = None
    _ready_init = None

    def __init__(
        self,
        bus,
        fmt,
        clock,
        reset=None,
        reset_active_level=True,
        ready_latency=0,
        ready_allowance=None,
        packets=None,
        strict_ready_latency=False,
        timeout_cycles=0,
        *args,
        **kwargs,
    ):
        if not isinstance(fmt, AvalonFormat):
            raise TypeError("fmt must be an AvalonFormat")
        self.fmt = fmt

        if ready_allowance is None:
            ready_allowance = ready_latency

        supported_ready_modes = [(0, 0), (1, 1)]

        if (ready_latency, ready_allowance) not in supported_ready_modes:
            raise NotImplementedError(
                f"Supported Avalon-ST ready modes are only "
                f"RL=0 RA=0 and RL=1 RA=1, got "
                f"RL={ready_latency} RA={ready_allowance}"
            )

        self.bus = bus
        self.clock = clock
        self.reset = reset
        self.reset_active_level = reset_active_level

        self.bus_label = self._format_bus_label(bus)
        self.log = logging.getLogger(f"cocotb.{self.bus_label}.{self._type}")

        self.log.info("Avalon-ST %s on %s", self._type, self.bus_label)

        self.active = False
        self.queue = Queue()
        self.beat_queue = Queue()
        self.dequeue_event = Event()
        self.current_frame = None
        self.idle_event = Event()
        self.idle_event.set()
        self.active_event = Event()
        self.wake_event = Event()

        self.queue_occupancy_symbols = 0
        self.queue_occupancy_frames = 0

        self.has_valid = hasattr(self.bus, "valid")
        self.has_ready = hasattr(self.bus, "ready")
        self.has_sop = hasattr(self.bus, "startofpacket")
        self.has_eop = hasattr(self.bus, "endofpacket")
        self.has_empty = hasattr(self.bus, "empty")
        self.has_error = hasattr(self.bus, "error")
        self.has_channel = hasattr(self.bus, "channel")

        self.has_packet_signals = self.has_sop and self.has_eop

        if packets is None:
            self.has_packets = self.has_packet_signals
        else:
            self.has_packets = bool(packets)
            if self.has_packets and not self.has_packet_signals:
                raise ValueError(
                    f"{self._bus_label()}: packets=True requires "
                    "startofpacket and endofpacket signals"
                )

        self.width = len(self.bus.data)

        if fmt is not None and self.width != fmt.payload_width:
            raise ValueError(
                f"{self._bus_label()}: AvalonFormat payload_width must match "
                f"Avalon-ST data width ({fmt.payload_width} != {self.width})"
            )

        self.bits_per_symbol = fmt.bits_per_symbol
        self.symbols_per_beat = fmt.symbols_per_beat

        if self.bits_per_symbol <= 0:
            raise ValueError("bits_per_symbol must be > 0")

        self.symbol_mask = (1 << self.bits_per_symbol) - 1

        
        if self.symbols_per_beat * self.bits_per_symbol > self.width:
            raise ValueError(
                f"{self._bus_label()}: symbols_per_beat * bits_per_symbol "
                f"exceeds Avalon-ST data width "
                f"({self.symbols_per_beat} * {self.bits_per_symbol} > {self.width})"
            )


        self.first_symbol_in_high_order_bits = fmt.first_symbol_in_high_order_bits

        self.ready_latency = ready_latency
        self.ready_allowance = ready_allowance
        self.strict_ready_latency = strict_ready_latency
        self._ready_history = [False] * self.ready_latency
        self.timeout_cycles = timeout_cycles

        if self._valid_init is not None and self.has_valid:
            self.bus.valid.value = Immediate(self._valid_init)

        if self._ready_init is not None and self.has_ready:
            self.bus.ready.value = Immediate(self._ready_init)

        if self._init_x:
            self._drive_x_initial()

        self.log.debug("Avalon-ST %s configuration:", self._type)
        self.log.debug("  Data width: %d bits", self.width)
        self.log.debug("  Bits per symbol: %d", self.bits_per_symbol)
        self.log.debug("  Symbols per beat: %d", self.symbols_per_beat)
        self.log.debug("  First symbol in high-order bits: %s", self.first_symbol_in_high_order_bits)
        self.log.debug("  Packets: %s", self.has_packets)
        self.log.debug("  Ready latency: %d", self.ready_latency)
        self.log.debug("  Ready allowance: %d", self.ready_allowance)

        self.log.debug("Avalon-ST %s signals:", self._type)
        for sig in ["data", "valid", "ready", "startofpacket", "endofpacket", "empty", "error", "channel"]:
            if hasattr(self.bus, sig):
                self.log.debug("  %s width: %d bits", sig, len(getattr(self.bus, sig)))
            else:
                self.log.debug("  %s: not present", sig)

        self._run_cr = None
        self._reset_monitor_cr = None
        self._reset_state = True
        self._init_reset_control()

    @staticmethod
    def _format_bus_label(bus):
        entity = getattr(bus, "_entity", None)
        entity_name = getattr(entity, "_name", None)
        bus_name = getattr(bus, "_name", None)

        if entity_name and bus_name:
            return f"{entity_name}.{bus_name}"
        if entity_name:
            return str(entity_name)
        if bus_name:
            return str(bus_name)
        return "avalon_st"

    def _bus_label(self):
        return getattr(self, "bus_label", self.log.name.removeprefix("cocotb."))

    def _protocol_context(self, beat=None):
        parts = [f"signals=({self._signal_snapshot()})"]
        if beat is not None:
            parts.append(f"beat={beat}")
        return ", ".join(parts)

    def _protocol_error(self, message, beat=None):
        return RuntimeError(
            f"{self._bus_label()}: Avalon-ST {self._type} {message}; "
            f"{self._protocol_context(beat)}"
        )

    def _logic_x(self, width):
        if LogicArray is not None:
            return LogicArray("x" * width)
        return "x" * width

    def _drive_x_initial(self):
        self.bus.data.value = Immediate(self._logic_x(len(self.bus.data)))

        for name in ["startofpacket", "endofpacket", "empty", "error", "channel"]:
            if hasattr(self.bus, name):
                sig = getattr(self.bus, name)
                sig.value = Immediate(self._logic_x(len(sig)))

    def _logic_bool(self, value, default=False):
        try:
            return bool(int(value))
        except ValueError:
            return default

    def _sample_reset_active(self):
        if self.reset is None:
            return False

        level = self._logic_bool(self.reset.value, default=bool(self.reset_active_level))
        return level == bool(self.reset_active_level)

    def _reset_active(self):
        return self._reset_state

    def _init_reset_control(self):
        self._reset_state = self._sample_reset_active()

        if self.reset is not None:
            self._reset_monitor_cr = cocotb.start_soon(self._run_reset_monitor())

        self._handle_reset(self._reset_state)

    async def _run_reset_monitor(self):
        while True:
            try:
                trigger = self.reset.value_change
            except AttributeError:
                trigger = Edge(self.reset)
            await trigger
            self._update_reset(self._sample_reset_active())

    def _update_reset(self, state):
        state = bool(state)
        if self._reset_state != state:
            self._reset_state = state
            self._handle_reset(state)

    def _handle_reset(self, state):
        if state:
            if self._run_cr is not None:
                self._run_cr.cancel()
                self._run_cr = None

            self.active = False
            self._reset_ready_state()

            if self.queue.empty():
                self.idle_event.set()
        else:
            if self._run_cr is None:
                self._run_cr = cocotb.start_soon(self._run())

    def _reset_ready_state(self):
        self._ready_history = [False] * self.ready_latency

    def count(self):
        return self.queue.qsize()

    def empty(self):
        return self.queue.empty()

    def clear(self):
        while not self.queue.empty():
            frame = self.queue.get_nowait()
            frame.sim_time_end = None
            frame.handle_tx_complete()

        while not self.beat_queue.empty():
            self.beat_queue.get_nowait()

        self.dequeue_event.set()
        self.idle_event.set()
        self.active_event.clear()
        self.queue_occupancy_symbols = 0
        self.queue_occupancy_frames = 0

    def _pack_symbols(self, symbols):
        value = 0

        for i, symbol in enumerate(symbols):
            symbol &= self.symbol_mask

            if self.first_symbol_in_high_order_bits:
                shift = (self.symbols_per_beat - 1 - i) * self.bits_per_symbol
            else:
                shift = i * self.bits_per_symbol

            value |= symbol << shift

        return value

    def _unpack_symbols(self, data_word):
        symbols = []

        for i in range(self.symbols_per_beat):
            if self.first_symbol_in_high_order_bits:
                shift = (self.symbols_per_beat - 1 - i) * self.bits_per_symbol
            else:
                shift = i * self.bits_per_symbol

            symbols.append((data_word >> shift) & self.symbol_mask)

        return symbols

    def _sample_ready_raw(self):
        if not self.has_ready:
            return True
        return self._logic_bool(self.bus.ready.value, default=False)

    def _sample_valid(self):
        if not self.has_valid:
            return True
        return self._logic_bool(self.bus.valid.value, default=False)

    def _sample_ready_qualified(self):
        raw_ready = self._sample_ready_raw()
        return self._ready_qualified_from_raw(raw_ready)

    def _ready_qualified_from_raw(self, raw_ready):
        if self.ready_latency == 0:
            return raw_ready

        # RL=1, RA=1:
        # ready asserted on cycle N qualifies transfer on cycle N+1.
        self._ready_history.append(raw_ready)
        return self._ready_history.pop(0)

    def cancel(self):
        if self._reset_monitor_cr is not None:
            self._reset_monitor_cr.cancel()
            self._reset_monitor_cr = None

        if self._run_cr is not None:
            self._run_cr.cancel()
            self._run_cr = None

    async def _run(self):
        raise NotImplementedError()


class AvalonSTPause:
    def _init_pause(self):
        self._pause = False
        self._pause_generator = None
        self._pause_cr = None

    @property
    def pause(self):
        return self._pause

    @pause.setter
    def pause(self, val):
        val = bool(val)
        if self._pause != val:
            self._pause_update(val)
        self._pause = val

    def _pause_update(self, val):
        pass

    def set_pause_generator(self, generator=None):
        self.clear_pause_generator()
        self._pause_generator = generator

        if self._pause_generator is not None:
            self._pause_cr = cocotb.start_soon(self._run_pause())

    def clear_pause_generator(self):
        if self._pause_cr is not None:
            self._pause_cr.cancel()
            self._pause_cr = None

        self._pause_generator = None

    async def _run_pause(self):
        clock_edge_event = RisingEdge(self.clock)

        for val in self._pause_generator:
            self.pause = val
            await clock_edge_event


class AvalonSTSource(AvalonSTBase, AvalonSTPause):
    _type = "source"

    _init_x = True
    _valid_init = 0
    _ready_init = None

    def __init__(
        self,
        bus,
        fmt,
        clock,
        reset=None,
        reset_active_level=True,
        ready_latency=0,
        ready_allowance=None,
        packets=None,
        idle_value="x",
        *args,
        **kwargs,
    ):
        self._init_pause()
        self.idle_value = idle_value

        super().__init__(
            bus,
            fmt,
            clock,
            reset,
            reset_active_level,
            ready_latency,
            ready_allowance,
            packets,
            *args,
            **kwargs,
        )

        self.queue_occupancy_limit_symbols = -1
        self.queue_occupancy_limit_frames = -1

    async def send(self, frame):
        while self.full():
            self.dequeue_event.clear()
            await self.dequeue_event.wait()

        if not isinstance(frame, AvalonSTFrame):
            frame = AvalonSTFrame(frame)

        await self.queue.put(frame)
        self.idle_event.clear()
        self.active_event.set()
        self.queue_occupancy_symbols += len(frame)
        self.queue_occupancy_frames += 1

    def send_nowait(self, frame):
        if self.full():
            raise QueueFull()

        if not isinstance(frame, AvalonSTFrame):
            frame = AvalonSTFrame(frame)

        self.queue.put_nowait(frame)
        self.idle_event.clear()
        self.active_event.set()
        self.queue_occupancy_symbols += len(frame)
        self.queue_occupancy_frames += 1

    async def write(self, data):
        await self.send(data)

    def write_nowait(self, data):
        self.send_nowait(data)

    def full(self):
        if (
            self.queue_occupancy_limit_symbols > 0
            and self.queue_occupancy_symbols > self.queue_occupancy_limit_symbols
        ):
            return True

        if (
            self.queue_occupancy_limit_frames > 0
            and self.queue_occupancy_frames > self.queue_occupancy_limit_frames
        ):
            return True

        return False

    def idle(self):
        return self.empty() and not self.active

    async def wait(self):
        await self.idle_event.wait()

    def _handle_reset(self, state):
        if state:
            self._drive_idle(0)

            if self.current_frame:
                self.log.warning("Flushed transmit frame during reset: %s", self.current_frame)
                self.current_frame.handle_tx_complete()
                self.current_frame = None

        super()._handle_reset(state)

    def cancel(self):
        self.clear_pause_generator()
        super().cancel()

    def _drive_idle(self, idle_value=None):
        if idle_value is None:
            idle_value = self.idle_value

        if self.has_valid:
            self.bus.valid.value = 0

        if idle_value == "x":
            self.bus.data.value = "x" * len(self.bus.data)

            if self.has_sop:
                self.bus.startofpacket.value = "x" * len(self.bus.startofpacket)
            if self.has_eop:
                self.bus.endofpacket.value = "x" * len(self.bus.endofpacket)
            if self.has_empty:
                self.bus.empty.value = "x" * len(self.bus.empty)
            if self.has_error:
                self.bus.error.value = "x" * len(self.bus.error)
            if self.has_channel:
                self.bus.channel.value = "x" * len(self.bus.channel)

        elif idle_value == "random":
            self.bus.data.value = random.getrandbits(self.width)

            if self.has_sop:
                self.bus.startofpacket.value = random.getrandbits(len(self.bus.startofpacket))
            if self.has_eop:
                self.bus.endofpacket.value = random.getrandbits(len(self.bus.endofpacket))
            if self.has_empty:
                self.bus.empty.value = random.randrange(0, max(1, self.symbols_per_beat))
            if self.has_error:
                self.bus.error.value = random.getrandbits(len(self.bus.error))
            if self.has_channel:
                self.bus.channel.value = random.getrandbits(len(self.bus.channel))

        else:
            bit = 0 if int(idle_value) == 0 else 1
            value = 0 if bit == 0 else (1 << self.width) - 1

            self.bus.data.value = value

            if self.has_sop:
                self.bus.startofpacket.value = bit
            if self.has_eop:
                self.bus.endofpacket.value = bit
            if self.has_empty:
                self.bus.empty.value = 0 if bit == 0 else (1 << len(self.bus.empty)) - 1
            if self.has_error:
                self.bus.error.value = 0 if bit == 0 else (1 << len(self.bus.error)) - 1
            if self.has_channel:
                self.bus.channel.value = 0 if bit == 0 else (1 << len(self.bus.channel)) - 1

    def _drive_beat(self, data_word, sop, eop, empty, error, channel):
        if self.has_valid:
            self.bus.valid.value = 1

        self.bus.data.value = data_word

        if self.has_sop:
            self.bus.startofpacket.value = int(sop) if self.has_packets else 0
        if self.has_eop:
            self.bus.endofpacket.value = int(eop) if self.has_packets else 0
        if self.has_empty:
            self.bus.empty.value = int(empty) if self.has_packets else 0
        if self.has_error:
            self.bus.error.value = int(error)
        if self.has_channel:
            self.bus.channel.value = int(channel)

    async def _run(self):
        frame = None
        frame_offset = 0
        self.active = False

        clock_edge_event = RisingEdge(self.clock)

        self._drive_idle()

        while True:
            await clock_edge_event

            if self._reset_active():
                self._drive_idle(0)
                self._reset_ready_state()

                if self.current_frame:
                    self.log.warning("Flushed transmit frame during reset: %s", self.current_frame)
                    self.current_frame.handle_tx_complete()
                    self.current_frame = None

                frame = None
                frame_offset = 0
                self.active = False

                if self.queue.empty():
                    self.idle_event.set()

                continue

            if self.ready_latency == 0:
                ready_sample = self._sample_ready_qualified()
                valid_sample = self._sample_valid()

                can_update_bus = (ready_sample and valid_sample) or not valid_sample

                if not can_update_bus:
                    continue

            else:
                # RL=1, RA=1:
                # source may drive valid/data only if ready is asserted now.
                # DUT/sink accepts this data on the next clock.
                ready_sample = self._sample_ready_raw()

                if not ready_sample:
                    self._drive_idle()
                    self.active = frame is not None or not self.queue.empty()
                    continue

            if frame is None and not self.queue.empty():
                frame = self.queue.get_nowait()
                self.dequeue_event.set()

                self.queue_occupancy_symbols -= len(frame)
                self.queue_occupancy_frames -= 1

                self.current_frame = frame
                frame.sim_time_start = get_sim_time()
                frame.sim_time_end = None
                self.log.debug("TX frame: %s", frame)

                self.active = True
                frame_offset = 0

            if frame is not None and not self.pause:
                remaining = len(frame.data) - frame_offset
                take = min(self.symbols_per_beat, remaining)

                symbols = frame.data[frame_offset:frame_offset + take]
                empty = self.symbols_per_beat - take

                while len(symbols) < self.symbols_per_beat:
                    symbols.append(0)

                data_word = self._pack_symbols(symbols)
                last = frame_offset + take >= len(frame.data)

                sop = self.has_packets and frame_offset == 0
                eop = self.has_packets and last
                empty_value = empty if eop else 0

                if type(frame.error) in (list, tuple):
                    error = frame.error[frame_offset] if frame_offset < len(frame.error) else frame.error[-1]
                elif frame.error is not None:
                    error = frame.error
                else:
                    error = 0

                if type(frame.channel) in (list, tuple):
                    channel = frame.channel[frame_offset] if frame_offset < len(frame.channel) else frame.channel[-1]
                elif frame.channel is not None:
                    channel = frame.channel
                else:
                    channel = 0

                self._drive_beat(
                    data_word=data_word,
                    sop=sop,
                    eop=eop,
                    empty=empty_value,
                    error=error,
                    channel=channel,
                )

                frame_offset += take

                if last:
                    frame.sim_time_end = get_sim_time()
                    frame.handle_tx_complete()
                    frame = None
                    self.current_frame = None

            else:
                self._drive_idle()

                self.active = frame is not None

                if frame is None and self.queue.empty():
                    self.idle_event.set()
                    self.active_event.clear()
                    await self.active_event.wait()


class AvalonSTMonitor(AvalonSTBase):
    _type = "monitor"

    _init_x = False
    _valid_init = None
    _ready_init = None

    def __init__(
        self,
        bus,
        fmt,
        clock,
        reset=None,
        reset_active_level=True,
        ready_latency=0,
        ready_allowance=None,
        packets=None,
        *args,
        **kwargs,
    ):
        super().__init__(
            bus,
            fmt,
            clock,
            reset,
            reset_active_level,
            ready_latency,
            ready_allowance,
            packets,
            *args,
            **kwargs,
        )

        self.read_queue = []

        self._signal_monitor_crs = []

        # RL=0 can sleep until activity resumes; RL=1 samples on every edge.
        # Do not register unused ValueChange callbacks for RL=1.
        if self.ready_latency == 0:
            if self.has_valid:
                self._signal_monitor_crs.append(
                    cocotb.start_soon(self._run_valid_monitor())
                )
            if self.has_ready:
                self._signal_monitor_crs.append(
                    cocotb.start_soon(self._run_ready_monitor())
                )

    def cancel(self):
        for task in self._signal_monitor_crs:
            task.cancel()
        self._signal_monitor_crs = []

        super().cancel()

    def _dequeue(self, frame):
        pass

    def _recv(self, frame):
        if self.queue.empty():
            self.active_event.clear()

        self.queue_occupancy_symbols -= len(frame)
        self.queue_occupancy_frames -= 1

        self._dequeue(frame)
        return frame

    async def recv(self):
        frame = await self.queue.get()
        return self._recv(frame)

    def recv_nowait(self):
        frame = self.queue.get_nowait()
        return self._recv(frame)

    async def recv_beat(self):
        return await self.beat_queue.get()

    def recv_beat_nowait(self):
        return self.beat_queue.get_nowait()

    async def read(self, count=-1):
        while not self.read_queue:
            frame = await self.recv()
            self.read_queue.extend(frame.data)

        return self.read_nowait(count)

    def read_nowait(self, count=-1):
        while not self.empty():
            frame = self.recv_nowait()
            self.read_queue.extend(frame.data)

        if count < 0:
            count = len(self.read_queue)

        data = self.read_queue[:count]
        del self.read_queue[:count]
        return data

    def idle(self):
        return not self.active

    async def wait(self, timeout=0, timeout_unit="ns"):
        if not self.empty():
            return

        if timeout:
            await First(self.active_event.wait(), Timer(timeout, timeout_unit))
        else:
            await self.active_event.wait()

    async def _run_valid_monitor(self):
        await self._run_rising_value_monitor(self.bus.valid, "valid")

    async def _run_ready_monitor(self):
        await self._run_rising_value_monitor(self.bus.ready, "ready")

    async def _run_rising_value_monitor(self, signal, signal_name):
        try:
            width = len(signal)
        except TypeError:
            width = 1

        if width != 1:
            raise TypeError(
                f"{self._bus_label()}: Avalon-ST {signal_name} must be "
                "scalar or 1-bit wide"
            )

        previous = self._signal_bool(signal)
        event = ValueChange(signal)
        while True:
            await event
            current = self._signal_bool(signal)

            if current and not previous:
                self.wake_event.set()

            previous = current

    def _signal_bool(self, signal):
        try:
            return bool(int(signal.value))
        except ValueError:
            return False

    @staticmethod
    def _format_bus_label(bus):
        entity = getattr(bus, "_entity", None)
        entity_name = getattr(entity, "_name", None)
        bus_name = getattr(bus, "_name", None)

        if entity_name and bus_name:
            return f"{entity_name}.{bus_name}"
        if entity_name:
            return str(entity_name)
        if bus_name:
            return str(bus_name)
        return "avalon_st"

    def _bus_label(self):
        return getattr(self, "bus_label", self.log.name.removeprefix("cocotb."))

    def _protocol_context(self, beat=None):
        parts = [f"signals=({self._signal_snapshot()})"]
        if beat is not None:
            parts.append(f"beat={beat}")
        return ", ".join(parts)

    def _protocol_error(self, message, beat=None):
        return RuntimeError(
            f"{self._bus_label()}: Avalon-ST {self._type} {message}; "
            f"{self._protocol_context(beat)}"
        )

    def _signal_snapshot(self):
        names = (
            "valid",
            "ready",
            "startofpacket",
            "endofpacket",
            "empty",
            "channel",
            "error",
            "data",
        )
        parts = []
        for name in names:
            if hasattr(self.bus, name):
                parts.append(f"{name}={getattr(self.bus, name).value}")
        return ", ".join(parts)

    def _safe_int(self, value, signal_name):
        try:
            return int(value)
        except ValueError as exc:
            raise RuntimeError(
                f"{self._bus_label()}: Avalon-ST {signal_name} is X/Z "
                f"during valid-ready handshake ({self._signal_snapshot()})"
            ) from exc

    def _safe_optional_int(self, value, default=0):
        try:
            return int(value)
        except ValueError:
            return default

    def _capture_beat(self):
        data_word = self._safe_int(self.bus.data.value, "data")

        if self.has_packets:
            sop = bool(self._safe_int(self.bus.startofpacket.value, "startofpacket"))
            eop = bool(self._safe_int(self.bus.endofpacket.value, "endofpacket"))
        else:
            sop = True
            eop = True

        raw_empty = 0
        if self.has_empty and self.has_packets and self.symbols_per_beat > 1:
            raw_empty = self._safe_optional_int(self.bus.empty.value, 0)

            if raw_empty:
                if not eop:
                    raise self._protocol_error(
                        f"empty={raw_empty} asserted without endofpacket"
                    )

                if raw_empty >= self.symbols_per_beat:
                    raise self._protocol_error(
                        f"empty out of range: {raw_empty}, "
                        f"symbols_per_beat={self.symbols_per_beat}"
                    )

        error = self._safe_optional_int(self.bus.error.value, 0) if self.has_error else 0
        channel = self._safe_optional_int(self.bus.channel.value, 0) if self.has_channel else 0

        symbols = self._unpack_symbols(data_word)

        if self.has_packets and eop and raw_empty:
            symbols = symbols[:-raw_empty]

        return AvalonSTBeat(
            data=data_word,
            symbols=symbols,
            sop=int(sop),
            eop=int(eop),
            empty=raw_empty,
            error=error,
            channel=channel,
            sim_time=get_sim_time(),
        )

    def _process_beat(self, beat, frame):
        self.beat_queue.put_nowait(beat)

        if self.has_packets:
            if beat.sop:
                if frame is not None:
                    raise self._protocol_error(
                        "duplicate startofpacket before endofpacket "
                        f"(open_frame_start={frame.sim_time_start}, "
                        f"open_frame_symbols={len(frame)})",
                        beat,
                    )

                frame = AvalonSTFrame([])
                frame.sim_time_start = get_sim_time()
                self.active = True

            elif frame is None:
                raise self._protocol_error(
                    "transfer outside of packet: missing startofpacket",
                    beat,
                )

            frame.data.extend(beat.symbols)

            if self.has_error:
                frame.error = beat.error
            if self.has_channel:
                frame.channel = beat.channel

            if beat.eop:
                frame.empty = beat.empty if self.has_empty else None
                frame.sim_time_end = get_sim_time()

                self.log.debug("RX frame: %s", frame)

                self.queue_occupancy_symbols += len(frame)
                self.queue_occupancy_frames += 1

                self.queue.put_nowait(frame)
                self.active_event.set()

                frame = None

        else:
            frame = AvalonSTFrame(beat.symbols)
            frame.sim_time_start = get_sim_time()
            frame.sim_time_end = get_sim_time()

            if self.has_error:
                frame.error = beat.error
            if self.has_channel:
                frame.channel = beat.channel
            if self.has_empty:
                frame.empty = beat.empty

            self.log.debug("RX frame: %s", frame)

            self.queue_occupancy_symbols += len(frame)
            self.queue_occupancy_frames += 1

            self.queue.put_nowait(frame)
            self.active_event.set()

            frame = None

        return frame

    async def _run(self):
        if self.ready_latency == 0:
            await self._run_rl0()
        elif self.ready_latency == 1:
            await self._run_rl1()
        else:
            raise NotImplementedError("AvalonSTMonitor supports only RL=0 or RL=1")

    def _check_timeout(self, idle_cycles):
        if self.timeout_cycles and idle_cycles >= self.timeout_cycles:
            raise TimeoutError(
                f"{self._bus_label()}: Avalon-ST {self._type} timeout: "
                f"no transfer for {idle_cycles} cycles; {self._protocol_context()}"
            )


    async def _run_rl0(self):
        frame = None
        self.active = False
        idle_cycles = 0

        clock_edge_event = RisingEdge(self.clock)
        wake_event = self.wake_event.wait()

        while True:
            await clock_edge_event

            if self._reset_active():
                frame = None
                self.active = False
                idle_cycles = 0
                self._reset_ready_state()
                continue

            ready_sample = self._sample_ready_qualified()
            valid_sample = self._sample_valid()

            if ready_sample and valid_sample:
                idle_cycles = 0
                beat = self._capture_beat()
                frame = self._process_beat(beat, frame)

            else:
                idle_cycles += 1
                self._check_timeout(idle_cycles)
                self.active = frame is not None

                # self.wake_event.clear()
                # await wake_event
                if self.timeout_cycles == 0:
                    self.wake_event.clear()
                    await wake_event

    async def _run_rl1(self):
        frame = None
        self.active = False

        clock_edge_event = RisingEdge(self.clock)

        prev_ready_raw = True
        idle_cycles = 0

        while True:
            await clock_edge_event
            await ReadOnly()

            if self._reset_active():
                frame = None
                self.active = False
                prev_ready_raw = True
                idle_cycles = 0
                self._reset_ready_state()
                continue

            ready_raw = self._sample_ready_raw()
            ready_sample = self._ready_qualified_from_raw(ready_raw)
            valid_sample = self._sample_valid()

            if self.strict_ready_latency and self.has_ready and self.has_valid:
                if not prev_ready_raw and valid_sample:
                    raise self._protocol_error(
                        "RL=1 violation: valid is asserted although ready "
                        "was low in the previous cycle"
                    )

            prev_ready_raw = ready_raw

            if ready_sample and valid_sample:
                idle_cycles = 0
                beat = self._capture_beat()
                frame = self._process_beat(beat, frame)
            else:
                idle_cycles += 1

                if self.timeout_cycles and idle_cycles >= self.timeout_cycles:
                    raise TimeoutError(
                        f"{self._bus_label()}: Avalon-ST {self._type} timeout: "
                        f"no transfer for {idle_cycles} cycles; "
                        f"{self._protocol_context()}"
                    )

                self.active = frame is not None

class AvalonSTSink(AvalonSTMonitor, AvalonSTPause):
    _type = "sink"

    _init_x = False
    _valid_init = None
    _ready_init = 0

    def __init__(
        self,
        bus,
        fmt,
        clock,
        reset=None,
        reset_active_level=True,
        ready_latency=0,
        ready_allowance=None,
        packets=None,
        *args,
        **kwargs,
    ):
        self._init_pause()

        self.queue_occupancy_limit_symbols = -1
        self.queue_occupancy_limit_frames = -1

        super().__init__(
            bus,
            fmt,
            clock,
            reset,
            reset_active_level,
            ready_latency,
            ready_allowance,
            packets,
            *args,
            **kwargs,
        )

    def full(self):
        if (
            self.queue_occupancy_limit_symbols > 0
            and self.queue_occupancy_symbols > self.queue_occupancy_limit_symbols
        ):
            return True

        if (
            self.queue_occupancy_limit_frames > 0
            and self.queue_occupancy_frames > self.queue_occupancy_limit_frames
        ):
            return True

        return False

    def _handle_reset(self, state):
        if state and self.has_ready:
            self.bus.ready.value = 0

        super()._handle_reset(state)

    def _pause_update(self, val):
        self.wake_event.set()

    def _dequeue(self, frame):
        self.wake_event.set()

    def cancel(self):
        self.clear_pause_generator()
        super().cancel()

    async def _run(self):
        if self.ready_latency == 0:
            await self._run_rl0()
        elif self.ready_latency == 1:
            await self._run_rl1()
        else:
            raise NotImplementedError("AvalonSTSink supports only RL=0 or RL=1")
        
    async def _run_rl0(self):
        frame = None
        self.active = False

        clock_edge_event = RisingEdge(self.clock)
        wake_event = self.wake_event.wait()

        if self.has_ready:
            self.bus.ready.value = 0

        while True:
            pause_sample = bool(self.pause)

            await clock_edge_event

            if self._reset_active():
                frame = None
                self.active = False
                self._reset_ready_state()

                if self.has_ready:
                    self.bus.ready.value = 0

                continue

            ready_sample = self._sample_ready_qualified()
            valid_sample = self._sample_valid()

            if ready_sample and valid_sample:
                beat = self._capture_beat()
                frame = self._process_beat(beat, frame)
            else:
                self.active = frame is not None

            if self.has_ready:
                paused = self.full() or pause_sample
                self.bus.ready.value = int(not paused)

                if (not valid_sample or paused) and (pause_sample == bool(self.pause)):
                    self.wake_event.clear()
                    await wake_event
            else:
                if not valid_sample:
                    self.wake_event.clear()
                    await wake_event

    async def _run_rl1(self):
        frame = None
        self.active = False

        clock_edge_event = RisingEdge(self.clock)

        prev_ready = False

        if self.has_ready:
            self.bus.ready.value = 0

        while True:
            await clock_edge_event

            reset_active = self._reset_active()

            # ready from previous cycle qualifies current transfer
            ready_sample = prev_ready

            # drive ready for NEXT cycle
            if self.has_ready:
                if reset_active:
                    next_ready = False
                else:
                    next_ready = not (self.full() or bool(self.pause))

                self.bus.ready.value = int(next_ready)
                prev_ready = next_ready
            else:
                prev_ready = True

            await ReadOnly()

            if reset_active:
                frame = None
                self.active = False
                self._reset_ready_state()
                continue

            valid_sample = self._sample_valid()

            if ready_sample and valid_sample:
                beat = self._capture_beat()
                frame = self._process_beat(beat, frame)
            else:
                self.active = frame is not None
