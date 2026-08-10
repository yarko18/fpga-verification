# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

from types import SimpleNamespace
import unittest

from fpga_verification.sim.stream_metrics import (
    PacketObservation,
    StreamPerformanceAnalyzer,
)


def _frame(start, end):
    return SimpleNamespace(sim_time_start=start, sim_time_end=end)


class StreamPerformanceAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = StreamPerformanceAnalyzer(clock_period_steps=10)
        self.observations = [
            PacketObservation("packet[0]", 3, _frame(100, 120), _frame(150, 170)),
            PacketObservation("packet[1]", 3, _frame(130, 150), _frame(200, 220)),
            PacketObservation("packet[2]", 3, _frame(160, 180), _frame(250, 270)),
        ]

    def test_packet_metrics(self):
        metrics = self.analyzer.packet(self.observations[0])

        self.assertEqual(metrics.input_cycles, 3)
        self.assertEqual(metrics.output_cycles, 3)
        self.assertEqual(metrics.sop_latency, 5)
        self.assertEqual(metrics.eop_latency, 5)
        self.assertEqual(metrics.end_to_end_cycles, 8)
        self.assertEqual(metrics.input_efficiency, 1)
        self.assertEqual(metrics.output_efficiency, 1)

    def test_sequence_metrics_and_clock_scaling(self):
        metrics = self.analyzer.sequence("burst", self.observations)

        self.assertEqual(metrics.total_beats, 9)
        self.assertEqual(metrics.input_cycles, 9)
        self.assertEqual(metrics.output_cycles, 13)
        self.assertEqual(metrics.input_packet_gaps, (0, 0))
        self.assertEqual(metrics.output_packet_gaps, (2, 2))
        self.assertEqual(metrics.input_sop_intervals, (3, 3))
        self.assertEqual(metrics.output_sop_intervals, (5, 5))
        self.assertEqual(metrics.boundary_overlaps, (True, True))
        self.assertEqual(metrics.max_packets_in_flight, 3)
        self.assertAlmostEqual(metrics.sustainable_efficiency, 9 / 13)
        self.assertAlmostEqual(metrics.required_clock_multiplier, 13 / 9)
        self.assertAlmostEqual(metrics.effective_ideal_clock(100), 900 / 13)
        self.assertAlmostEqual(metrics.required_clock_for_ideal(100), 1300 / 9)

        metrics.assert_input_packet_gap_at_most(0)
        metrics.assert_all_boundaries_overlap()

    def test_gap_limit_reports_the_packet_boundary(self):
        observations = [
            self.observations[0],
            PacketObservation(
                "packet[1]",
                3,
                _frame(150, 170),
                _frame(200, 220),
            ),
        ]
        metrics = self.analyzer.sequence("stalled burst", observations)

        with self.assertRaisesRegex(
            AssertionError,
            r"packet\[0\]->packet\[1\]: 2 cycles",
        ):
            metrics.assert_input_packet_gap_at_most(0)

    def test_rejects_timestamps_not_aligned_to_the_clock(self):
        observation = PacketObservation(
            "unaligned",
            1,
            _frame(0, 11),
            _frame(20, 20),
        )

        with self.assertRaisesRegex(ValueError, "not aligned"):
            self.analyzer.packet(observation)


if __name__ == "__main__":
    unittest.main()
