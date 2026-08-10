# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

"""Reusable performance metrics for packetized streaming interfaces."""

from dataclasses import dataclass
from statistics import fmean
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class PacketObservation:
    """One packet observed at the input and output of a DUT or pipeline."""

    name: str
    beats: int
    input_frame: Any
    output_frame: Any


@dataclass(frozen=True)
class PacketMetrics:
    """Latency and throughput metrics for one packet."""

    name: str
    beats: int
    input_cycles: int
    input_efficiency: float
    input_stalls: int
    output_cycles: int
    output_efficiency: float
    output_bubbles: int
    sop_latency: int
    eop_latency: int
    end_to_end_cycles: int

    def log(self, logger):
        logger.info(
            "%s metrics:\n beats=%d,\n input=%d cycles "
            "(%.2f%%, stalls=%d),\n output=%d cycles "
            "(%.2f%%, bubbles=%d),\n SoP latency=%d,\n "
            "EoP latency=%d,\n end-to-end=%d cycles",
            self.name,
            self.beats,
            self.input_cycles,
            self.input_efficiency * 100,
            self.input_stalls,
            self.output_cycles,
            self.output_efficiency * 100,
            self.output_bubbles,
            self.sop_latency,
            self.eop_latency,
            self.end_to_end_cycles,
        )


@dataclass(frozen=True)
class PacketSequenceMetrics:
    """Throughput and packet-boundary metrics for an ordered packet sequence."""

    name: str
    packets: tuple[PacketMetrics, ...]
    total_beats: int
    input_cycles: int
    input_efficiency: float
    input_stalls: int
    output_cycles: int
    output_efficiency: float
    output_bubbles: int
    input_packet_gaps: tuple[int, ...]
    output_packet_gaps: tuple[int, ...]
    input_sop_intervals: tuple[int, ...]
    output_sop_intervals: tuple[int, ...]
    boundary_overlaps: tuple[bool, ...]
    max_packets_in_flight: int

    @property
    def max_input_packet_gap(self):
        return max(self.input_packet_gaps, default=0)

    @property
    def max_output_packet_gap(self):
        return max(self.output_packet_gaps, default=0)

    @property
    def sustainable_efficiency(self):
        """Conservative sustained throughput relative to one beat per cycle."""

        return min(self.input_efficiency, self.output_efficiency)

    @property
    def required_clock_multiplier(self):
        """Clock multiplier needed to match an ideal one-beat/cycle stream."""

        return 1 / self.sustainable_efficiency

    def assert_input_packet_gap_at_most(self, maximum_cycles):
        """Require every next input SoP to be accepted within the limit."""

        violating = [
            (index, gap)
            for index, gap in enumerate(self.input_packet_gaps)
            if gap > maximum_cycles
        ]
        if violating:
            details = ", ".join(
                f"{self.packets[index].name}->{self.packets[index + 1].name}: "
                f"{gap} cycles"
                for index, gap in violating
            )
            raise AssertionError(
                f"{self.name}: input packet gap exceeds {maximum_cycles} cycles: "
                f"{details}"
            )

    def assert_all_boundaries_overlap(self):
        """Require the next packet to enter before the previous packet exits."""

        missing = [
            index
            for index, overlaps in enumerate(self.boundary_overlaps)
            if not overlaps
        ]
        if missing:
            details = ", ".join(
                f"{self.packets[index].name}->{self.packets[index + 1].name}"
                for index in missing
            )
            raise AssertionError(
                f"{self.name}: packet boundaries without pipeline overlap: {details}"
            )

    def log(self, logger):
        logger.info(
            "%s sequence metrics:\n packets=%d, beats=%d,\n "
            "input=%d cycles (%.2f%%, stalls=%d),\n "
            "output=%d cycles (%.2f%%, bubbles=%d),\n "
            "input packet gaps=%s (max=%d),\n "
            "output packet gaps=%s (max=%d),\n "
            "input SoP intervals=%s,\n output SoP intervals=%s,\n "
            "overlapping boundaries=%d/%d, max packets in flight=%d,\n "
            "sustainable efficiency=%.2f%%, required clock multiplier=%.4fx",
            self.name,
            len(self.packets),
            self.total_beats,
            self.input_cycles,
            self.input_efficiency * 100,
            self.input_stalls,
            self.output_cycles,
            self.output_efficiency * 100,
            self.output_bubbles,
            _format_samples(self.input_packet_gaps),
            self.max_input_packet_gap,
            _format_samples(self.output_packet_gaps),
            self.max_output_packet_gap,
            _format_samples(self.input_sop_intervals),
            _format_samples(self.output_sop_intervals),
            sum(self.boundary_overlaps),
            len(self.boundary_overlaps),
            self.max_packets_in_flight,
            self.sustainable_efficiency * 100,
            self.required_clock_multiplier,
        )


class StreamPerformanceAnalyzer:
    """Calculate cycle-based metrics from timestamped monitor frames.

    Frames must expose ``sim_time_start`` and ``sim_time_end`` attributes, as
    ``AvalonSTFrame`` does. The analyzer is otherwise independent of packet
    contents and can therefore measure a single IP or a complete pipeline.
    """

    def __init__(self):
        self._clock_period_steps = None

    @classmethod
    async def from_clock(cls, clock):
        """Measure the simulation clock period without requiring its frequency."""

        from cocotb.triggers import RisingEdge
        from cocotb.utils import get_sim_time

        analyzer = cls()
        await RisingEdge(clock)
        start = get_sim_time(unit="step")
        await RisingEdge(clock)
        end = get_sim_time(unit="step")
        analyzer._set_clock_period_steps(end - start)
        return analyzer

    @classmethod
    def _from_clock_period_steps(cls, clock_period_steps):
        """Construct an analyzer with a known period for unit testing."""

        analyzer = cls()
        analyzer._set_clock_period_steps(clock_period_steps)
        return analyzer

    def _set_clock_period_steps(self, clock_period_steps):
        clock_period_steps = int(clock_period_steps)
        if clock_period_steps <= 0:
            raise ValueError("clock_period_steps must be greater than zero")
        self._clock_period_steps = clock_period_steps

    def packet(self, observation):
        self._validate_observation(observation)

        input_cycles = self._frame_cycles(observation.input_frame)
        output_cycles = self._frame_cycles(observation.output_frame)

        return PacketMetrics(
            name=observation.name,
            beats=observation.beats,
            input_cycles=input_cycles,
            input_efficiency=observation.beats / input_cycles,
            input_stalls=input_cycles - observation.beats,
            output_cycles=output_cycles,
            output_efficiency=observation.beats / output_cycles,
            output_bubbles=output_cycles - observation.beats,
            sop_latency=self._cycle_delta(
                observation.input_frame.sim_time_start,
                observation.output_frame.sim_time_start,
            ),
            eop_latency=self._cycle_delta(
                observation.input_frame.sim_time_end,
                observation.output_frame.sim_time_end,
            ),
            end_to_end_cycles=self._cycle_delta(
                observation.input_frame.sim_time_start,
                observation.output_frame.sim_time_end,
            ) + 1,
        )

    def sequence(self, name, observations: Sequence[PacketObservation]):
        observations = tuple(observations)
        if not observations:
            raise ValueError("observations must contain at least one packet")

        for observation in observations:
            self._validate_observation(observation)

        packets = tuple(self.packet(observation) for observation in observations)
        total_beats = sum(packet.beats for packet in packets)

        input_cycles = self._cycle_delta(
            observations[0].input_frame.sim_time_start,
            observations[-1].input_frame.sim_time_end,
        ) + 1
        output_cycles = self._cycle_delta(
            observations[0].output_frame.sim_time_start,
            observations[-1].output_frame.sim_time_end,
        ) + 1

        input_packet_gaps = tuple(
            self._cycle_delta(
                previous.input_frame.sim_time_end,
                current.input_frame.sim_time_start,
            ) - 1
            for previous, current in _pairwise(observations)
        )
        output_packet_gaps = tuple(
            self._cycle_delta(
                previous.output_frame.sim_time_end,
                current.output_frame.sim_time_start,
            ) - 1
            for previous, current in _pairwise(observations)
        )
        input_sop_intervals = tuple(
            self._cycle_delta(
                previous.input_frame.sim_time_start,
                current.input_frame.sim_time_start,
            )
            for previous, current in _pairwise(observations)
        )
        output_sop_intervals = tuple(
            self._cycle_delta(
                previous.output_frame.sim_time_start,
                current.output_frame.sim_time_start,
            )
            for previous, current in _pairwise(observations)
        )
        boundary_overlaps = tuple(
            current.input_frame.sim_time_start <= previous.output_frame.sim_time_end
            for previous, current in _pairwise(observations)
        )

        if any(gap < 0 for gap in input_packet_gaps):
            raise ValueError("input packet observations overlap or are out of order")
        if any(gap < 0 for gap in output_packet_gaps):
            raise ValueError("output packet observations overlap or are out of order")

        return PacketSequenceMetrics(
            name=name,
            packets=packets,
            total_beats=total_beats,
            input_cycles=input_cycles,
            input_efficiency=total_beats / input_cycles,
            input_stalls=input_cycles - total_beats,
            output_cycles=output_cycles,
            output_efficiency=total_beats / output_cycles,
            output_bubbles=output_cycles - total_beats,
            input_packet_gaps=input_packet_gaps,
            output_packet_gaps=output_packet_gaps,
            input_sop_intervals=input_sop_intervals,
            output_sop_intervals=output_sop_intervals,
            boundary_overlaps=boundary_overlaps,
            max_packets_in_flight=_max_packets_in_flight(observations),
        )

    def _frame_cycles(self, frame):
        return self._cycle_delta(frame.sim_time_start, frame.sim_time_end) + 1

    def _cycle_delta(self, start, end):
        if self._clock_period_steps is None:
            raise RuntimeError(
                "StreamPerformanceAnalyzer is not calibrated; create it with "
                "'await StreamPerformanceAnalyzer.from_clock(clock)'"
            )
        delta_steps = int(end - start)
        cycles, remainder = divmod(delta_steps, self._clock_period_steps)
        if remainder:
            raise ValueError(
                f"timestamp difference {delta_steps} is not aligned to the "
                f"{self._clock_period_steps}-step clock period"
            )
        return cycles

    @staticmethod
    def _validate_observation(observation):
        if observation.beats <= 0:
            raise ValueError("packet beats must be greater than zero")

        for side, frame in (
            ("input", observation.input_frame),
            ("output", observation.output_frame),
        ):
            if frame.sim_time_start is None or frame.sim_time_end is None:
                raise ValueError(
                    f"{observation.name} {side} frame has incomplete timestamps"
                )
            if frame.sim_time_end < frame.sim_time_start:
                raise ValueError(
                    f"{observation.name} {side} frame ends before it starts"
                )


def _pairwise(values: Sequence[Any]) -> Iterable[tuple[Any, Any]]:
    return zip(values, values[1:])


def _max_packets_in_flight(observations):
    maximum = 0
    for index, observation in enumerate(observations):
        packets_in_flight = 1 + sum(
            previous.output_frame.sim_time_end
            >= observation.input_frame.sim_time_start
            for previous in observations[:index]
        )
        maximum = max(maximum, packets_in_flight)
    return maximum


def _format_samples(values):
    values = tuple(values)
    if len(values) <= 8:
        return str(list(values))
    return (
        f"count={len(values)}, min={min(values)}, "
        f"avg={fmean(values):.2f}, max={max(values)}"
    )
