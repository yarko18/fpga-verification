# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Reusable cycle-level functional coverage for Avalon-ST interfaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fpga_verification.sim.analysis import Subscriber
from fpga_verification.sim.coverage import CoverageGroup, CoverageScope


AVALON_ST_CYCLE_STATES = {
    (False, False): "idle",
    (True, False): "ready_only",
    (False, True): "valid_only",
    (True, True): "ready_valid",
}
"""Labels for the four raw ``(ready, valid)`` pin combinations."""

DEFAULT_BACKPRESSURE_BINS = {
    "none": (0, 0),
    "one": (1, 1),
    "short": (2, 3),
    "medium": (4, 7),
    "long": (8, None),
}
"""Default bins for completed transfers' backpressure duration in cycles."""


@dataclass(frozen=True)
class AvalonSTCycleSample:
    """Raw Avalon-ST handshake pins sampled on one clock edge."""

    ready: bool
    valid: bool
    reset_active: bool = False


class AvalonSTCycleCoverage(Subscriber[AvalonSTCycleSample]):
    """Collect raw cycle states and completed transfer stall durations.

    ``write`` accepts one sample per active clock edge. For ``ready_latency=1``,
    the previous cycle's raw ``ready`` value qualifies the current transfer,
    matching the RL=1/RA=1 mode supported by ``cocotbext-avalon``.
    """

    def __init__(
        self,
        scope: CoverageScope,
        *,
        ready_latency: int = 0,
        expected_states: Sequence[str] | None = None,
        backpressure_bins: Mapping[str, tuple[int, int | None]] | None = None,
        include_backpressure: bool = True,
    ):
        if ready_latency not in (0, 1):
            raise ValueError("ready_latency must be 0 or 1")

        self.scope = scope
        self.ready_latency = ready_latency
        self._effective_ready_latency = ready_latency
        self.include_backpressure = include_backpressure
        self._expected_states = (
            None if expected_states is None else tuple(expected_states)
        )
        self._backpressure_bins = dict(
            DEFAULT_BACKPRESSURE_BINS
            if backpressure_bins is None
            else backpressure_bins
        )
        self._validate_backpressure_bins(self._backpressure_bins)

        self._cycle_group: CoverageGroup | None = None
        self._backpressure_group: CoverageGroup | None = None
        self._previous_ready = False
        self._stalled_cycles = 0
        self._monitor_started = False
        self._monitor_signature = None

    @staticmethod
    def _validate_backpressure_bins(
        bins: Mapping[str, tuple[int, int | None]],
    ) -> None:
        if not bins:
            raise ValueError("backpressure_bins must not be empty")
        previous_high = -1
        entries = tuple(bins.items())
        for index, (name, bounds) in enumerate(entries):
            if not isinstance(name, str) or not name:
                raise ValueError("backpressure bin names must be non-empty strings")
            if (
                not isinstance(bounds, tuple)
                or len(bounds) != 2
                or not isinstance(bounds[0], int)
                or bounds[0] < 0
            ):
                raise ValueError(
                    f"backpressure bin {name!r} must use (minimum, maximum)"
                )
            low, high = bounds
            if low != previous_high + 1:
                raise ValueError("backpressure bins must be contiguous from zero")
            if high is None:
                if index != len(entries) - 1:
                    raise ValueError("only the last backpressure bin may be open-ended")
                previous_high = low
            else:
                if not isinstance(high, int) or high < low:
                    raise ValueError(
                        f"backpressure bin {name!r} has an invalid maximum"
                    )
                previous_high = high
        if entries[-1][1][1] is not None:
            raise ValueError("the last backpressure bin must be open-ended")

    @staticmethod
    def _reachable_states(has_ready: bool, has_valid: bool) -> tuple[str, ...]:
        ready_values = [False, True] if has_ready else [True]
        valid_values = [False, True] if has_valid else [True]
        reachable = {
            AVALON_ST_CYCLE_STATES[(ready, valid)]
            for ready in ready_values
            for valid in valid_values
        }
        return tuple(
            state for state in AVALON_ST_CYCLE_STATES.values() if state in reachable
        )

    def _initialize(
        self,
        expected_states: Sequence[str],
        *,
        include_backpressure: bool = True,
    ) -> None:
        from cocotb_coverage.coverage import CoverPoint

        states = tuple(expected_states)
        if any(not isinstance(state, str) for state in states):
            raise ValueError("expected_states entries must be strings")
        unknown = set(states) - set(AVALON_ST_CYCLE_STATES.values())
        if unknown:
            raise ValueError(
                "unknown Avalon-ST cycle states: " + ", ".join(sorted(unknown))
            )
        if not states:
            raise ValueError("expected_states must not be empty")
        if len(set(states)) != len(states):
            raise ValueError("expected_states must not contain duplicates")

        self._cycle_group = CoverageGroup(
            CoverPoint(
                self.scope.item("cycle_state"),
                bins=list(states),
            )
        )
        if include_backpressure:
            stall_bins = tuple(self._backpressure_bins)
            self._backpressure_group = CoverageGroup(
                CoverPoint(
                    self.scope.item("backpressure_cycles"),
                    xf=self._backpressure_bin,
                    bins=list(stall_bins),
                )
            )

    def _backpressure_bin(self, cycles: int) -> str:
        for name, (low, high) in self._backpressure_bins.items():
            if cycles >= low and (high is None or cycles <= high):
                return name
        raise ValueError(f"no backpressure bin configured for {cycles} cycles")

    def sample(
        self,
        ready: bool,
        valid: bool,
        *,
        reset_active: bool = False,
    ) -> None:
        """Sample one cycle; reset cycles are excluded and clear pending stalls."""
        if self._cycle_group is None:
            expected_states = (
                self._expected_states
                if self._expected_states is not None
                else tuple(AVALON_ST_CYCLE_STATES.values())
            )
            self._initialize(
                expected_states,
                include_backpressure=self.include_backpressure,
            )

        if reset_active:
            self._previous_ready = False
            self._stalled_cycles = 0
            return

        ready = bool(ready)
        valid = bool(valid)
        state = AVALON_ST_CYCLE_STATES[(ready, valid)]
        self._cycle_group.write(state)

        qualified_ready = ready
        if self._effective_ready_latency:
            qualified_ready = self._previous_ready
        self._previous_ready = ready

        if valid and qualified_ready:
            if self._backpressure_group is not None:
                self._backpressure_group.write(self._stalled_cycles)
            self._stalled_cycles = 0
        elif valid:
            self._stalled_cycles += 1
        else:
            # A dropped valid is not a completed transfer, so do not count its
            # partial wait as a completed backpressure observation.
            self._stalled_cycles = 0

    def write(self, item: AvalonSTCycleSample) -> None:
        """Accept one cycle sample through the shared Subscriber convention."""
        if not isinstance(item, AvalonSTCycleSample):
            raise TypeError("Avalon-ST cycle coverage expects AvalonSTCycleSample")
        self.sample(
            item.ready,
            item.valid,
            reset_active=item.reset_active,
        )

    async def monitor(
        self,
        bus,
        clock,
        *,
        reset=None,
        reset_active_level: bool = True,
    ) -> None:
        """Sample a bus once per rising edge without changing the BFM.

        The sidecar handles interfaces that omit ``ready`` or ``valid`` by
        treating a missing signal as permanently asserted and excluding the
        unreachable raw states from the denominator.
        """
        from cocotb.triggers import ReadOnly, RisingEdge

        if self._monitor_started:
            raise RuntimeError("Avalon-ST cycle coverage monitor is already active")
        self._monitor_started = True
        try:
            ready_signal = getattr(bus, "ready", None)
            valid_signal = getattr(bus, "valid", None)
            for name, signal in (
                ("ready", ready_signal),
                ("valid", valid_signal),
                ("reset", reset),
            ):
                if signal is None:
                    continue
                try:
                    width = len(signal)
                except TypeError:
                    width = 1
                if width != 1:
                    raise TypeError(
                        f"Avalon-ST {name} must be scalar or one bit wide"
                    )
            effective_ready_latency = (
                0 if ready_signal is None else self.ready_latency
            )
            expected_states = (
                self._expected_states
                if self._expected_states is not None
                else self._reachable_states(
                    has_ready=ready_signal is not None,
                    has_valid=valid_signal is not None,
                )
            )
            reachable_states = self._reachable_states(
                has_ready=ready_signal is not None,
                has_valid=valid_signal is not None,
            )
            impossible_states = set(expected_states) - set(reachable_states)
            if impossible_states:
                raise ValueError(
                    "expected Avalon-ST states cannot occur on this interface: "
                    + ", ".join(sorted(impossible_states))
                )
            include_backpressure = (
                self.include_backpressure and ready_signal is not None
            )
            signature = (
                tuple(expected_states),
                include_backpressure,
                effective_ready_latency,
                tuple(self._backpressure_bins.items()),
            )
            if self._cycle_group is None:
                self._initialize(
                    expected_states,
                    include_backpressure=include_backpressure,
                )
                self._monitor_signature = signature
            elif self._monitor_signature is None:
                raise RuntimeError(
                    "direct samples and bus monitoring cannot share one "
                    "Avalon-ST coverage model"
                )
            elif self._monitor_signature != signature:
                raise RuntimeError(
                    "one Avalon-ST coverage model cannot be reused with a "
                    "different interface profile"
                )
            self._effective_ready_latency = effective_ready_latency

            def read_bool(signal, default, name):
                if signal is None:
                    return default
                try:
                    return bool(int(signal.value))
                except (TypeError, ValueError) as error:
                    raise RuntimeError(
                        f"Avalon-ST {name} is unresolved while sampling coverage"
                    ) from error

            while True:
                await RisingEdge(clock)
                await ReadOnly()
                reset_is_active = (
                    reset is not None
                    and read_bool(reset, False, "reset") == reset_active_level
                )
                self.sample(
                    read_bool(ready_signal, True, "ready"),
                    read_bool(valid_signal, True, "valid"),
                    reset_active=reset_is_active,
                )
        finally:
            self._previous_ready = False
            self._stalled_cycles = 0
            self._monitor_started = False
