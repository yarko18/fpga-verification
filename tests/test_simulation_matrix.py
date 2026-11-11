# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from collections import Counter
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from fpga_verification.sim import (
    ComponentConfig,
    balance,
    exhaustive,
    hdl_parameter,
    matrix_parameter,
    random_subset,
)
from fpga_verification.sim._matrix_planning import (
    MatrixTest,
    ParameterMatrix,
    build_matrix_plan,
    discover_matrix_tests,
)


@dataclass(frozen=True)
class _Config(ComponentConfig):
    width: int = hdl_parameter(8, name="WIDTH", values=(8, 16, 24))
    lanes: int = hdl_parameter(1, name="LANES", values=(1, 2))
    operation: str = matrix_parameter("PAD", values=("PAD", "PACK"))
    note: str = "baseline"

    def __post_init__(self):
        if self.width * self.lanes > 32:
            raise ValueError("payload is too wide")


def _matrix_test(name, vary, strategy):
    return MatrixTest(f"matrix_tests.{name}", ParameterMatrix(tuple(vary), strategy))


def _items(config, names):
    return {(name, getattr(config, name)) for name in names}


def test_hdl_parameter_values_are_optional_until_a_test_varies_the_field():
    @dataclass(frozen=True)
    class Config(ComponentConfig):
        width: int = hdl_parameter(8, name="WIDTH")

    config = Config()
    assert config.to_parameters() == {"WIDTH": 8}

    with pytest.raises(ValueError, match="has no values"):
        build_matrix_plan(
            config,
            [_matrix_test("test_width", ("width",), exhaustive())],
        )


def test_invalid_post_init_candidates_are_filtered_not_reported_as_tests():
    plan = build_matrix_plan(
        _Config(),
        [_matrix_test("test_all", ("width", "lanes"), exhaustive())],
    )

    assert plan.candidates == 6
    assert plan.legal == 5
    assert plan.selected == 5
    assert len(plan.jobs) == 5
    assert plan.test_executions == 5


def test_balance_covers_every_reachable_value_and_keeps_baseline():
    names = ("width", "lanes", "operation")
    exhaustive_plan = build_matrix_plan(
        _Config(),
        [_matrix_test("test_all", names, exhaustive())],
    )
    compact_plan = build_matrix_plan(
        _Config(),
        [_matrix_test("test_all", names, balance())],
    )

    required = set().union(
        *(_items(job.config, names) for job in exhaustive_plan.jobs)
    )
    covered = set().union(
        *(_items(job.config, names) for job in compact_plan.jobs)
    )
    assert covered == required
    assert _Config() in [job.config for job in compact_plan.jobs]
    assert len(compact_plan.jobs) <= len(exhaustive_plan.jobs)


def test_balance_distributes_small_domain_values_evenly():
    @dataclass(frozen=True)
    class Config(ComponentConfig):
        width: int = hdl_parameter(0, name="WIDTH", values=range(8))
        operation: str = matrix_parameter(
            "A",
            values=("A", "B", "C", "D"),
        )

    plan = build_matrix_plan(
        Config(),
        [_matrix_test("test_balance", ("width", "operation"), balance())],
    )
    counts = Counter(job.config.operation for job in plan.jobs)

    assert len(plan.jobs) == 8
    assert set(counts) == {"A", "B", "C", "D"}
    assert max(counts.values()) - min(counts.values()) <= 1


def test_random_subset_is_bounded_and_reproducible():
    test = _matrix_test(
        "test_random",
        ("width", "lanes", "operation"),
        random_subset(count=4, seed=1234),
    )

    first = build_matrix_plan(_Config(), [test])
    second = build_matrix_plan(_Config(), [test])

    assert len(first.jobs) == 4
    assert [job.config_id for job in first.jobs] == [
        job.config_id for job in second.jobs
    ]


def test_random_subset_requires_a_positive_count():
    with pytest.raises(ValueError, match="count must be positive"):
        random_subset(count=0, seed=1234)


def test_tests_with_matching_configs_share_one_job():
    matrix = ParameterMatrix(("operation",), exhaustive())
    plan = build_matrix_plan(
        _Config(),
        [
            MatrixTest("matrix_tests.test_a", matrix),
            MatrixTest("matrix_tests.test_b", matrix),
        ],
    )

    assert len(plan.jobs) == 2
    assert plan.test_executions == 4
    assert all(
        job.tests == ["matrix_tests.test_a", "matrix_tests.test_b"]
        for job in plan.jobs
    )


def test_undecorated_test_runs_once_on_the_baseline():
    plan = build_matrix_plan(
        _Config(),
        [MatrixTest("matrix_tests.test_smoke")],
    )

    assert len(plan.jobs) == 1
    assert plan.jobs[0].config == _Config()
    assert plan.jobs[0].tests == ["matrix_tests.test_smoke"]


def test_discovery_filters_full_names_and_ignores_duplicate_objects(monkeypatch):
    cocotb_test_type = type("Test", (), {"__module__": "cocotb._decorators"})
    video_test = cocotb_test_type()
    video_test.name = "VideoPacketTest"
    video_test.fullname = "vip.test_pyuvm.VideoPacketTest"
    control_test = cocotb_test_type()
    control_test.name = "ControlPacketTest"
    control_test.fullname = "vip.test_pyuvm.ControlPacketTest"
    module = SimpleNamespace(
        video=video_test,
        video_alias=video_test,
        control=control_test,
    )
    monkeypatch.setattr(
        "fpga_verification.sim._matrix_planning.importlib.import_module",
        lambda name: module,
    )

    discovered = discover_matrix_tests("vip.test_pyuvm", ("Video*",))

    assert [test.fullname for test in discovered] == [
        "vip.test_pyuvm.VideoPacketTest"
    ]
