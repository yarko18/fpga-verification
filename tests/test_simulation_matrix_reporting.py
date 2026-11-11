# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

import json
from dataclasses import dataclass

from fpga_verification.sim import ComponentConfig, hdl_parameter
from fpga_verification.sim._matrix_planning import (
    MatrixStatus,
    MatrixTest,
    MatrixTestResult,
    build_matrix_plan,
)
from fpga_verification.sim._matrix_reporting import (
    ProgressReporter,
    print_summary,
    write_results,
)


@dataclass(frozen=True)
class _Config(ComponentConfig):
    width: int = hdl_parameter(8, name="WIDTH")


def _failed_plan():
    plan = build_matrix_plan(_Config(), [MatrixTest("matrix_tests.test_smoke")])
    job = plan.jobs[0]
    job.status = MatrixStatus.FAIL
    job.log_path = "logs/matrix_failures/12345678/simulation.log"
    job.results = [
        MatrixTestResult(
            "matrix_tests.test_smoke",
            MatrixStatus.FAIL,
            real_time_s=0.5,
            sim_time_ns=30.0,
        )
    ]
    return plan


def test_matrix_results_are_compact_and_keep_config_as_the_last_field(tmp_path):
    plan = _failed_plan()
    job = plan.jobs[0]

    result = json.loads(write_results(tmp_path, plan).read_text(encoding="utf-8"))

    assert result == [
        {
            "id": job.config_id,
            "status": "FAIL",
            "log": "logs/matrix_failures/12345678/simulation.log",
            "sim_time_ns": 30.0,
            "real_time_s": 0.5,
            "config": {"width": 8},
        }
    ]
    assert list(result[0]) == [
        "id",
        "status",
        "log",
        "sim_time_ns",
        "real_time_s",
        "config",
    ]


def test_summary_reports_test_totals_and_failed_configuration(capsys):
    plan = _failed_plan()

    print_summary(plan, elapsed=1.25)

    output = capsys.readouterr().out
    assert "matrix_tests.test_smoke" in output
    assert "CONFIGS=1 PASS=0 FAIL=1 ERROR=0 SKIP=0 RUNS=1" in output
    assert f"{plan.jobs[0].config_id}: matrix_tests.test_smoke" in output
    assert "width=8" in output


def test_progress_reports_completed_configs_and_runs(capsys):
    plan = _failed_plan()
    job = plan.jobs[0]
    job.wall_time_s = 0.25

    ProgressReporter(plan).report(job)

    assert capsys.readouterr().out == (
        f"[configs 1/1 | runs 1/1] {job.config_id} FAIL  0/1 runs 0.25s\n"
    )
