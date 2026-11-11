# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Terminal and JSON reporting for matrix simulations."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ._matrix_planning import MatrixJob, MatrixPlan, MatrixStatus


class ProgressReporter:
    """Track completed configurations and individual simulator test runs."""

    def __init__(self, plan: MatrixPlan):
        self.plan = plan
        self.completed_configs = 0
        self.completed_runs = 0

    def report(self, job: MatrixJob) -> None:
        self.completed_configs += 1
        self.completed_runs += len(job.tests)
        passed = sum(result.status is MatrixStatus.PASS for result in job.results)
        print(
            f"[configs {self.completed_configs}/{len(self.plan.jobs)} | "
            f"runs {self.completed_runs}/{self.plan.test_executions}] "
            f"{job.config_id} {job.status:<5} "
            f"{passed}/{len(job.tests)} runs {job.wall_time_s:.2f}s",
            flush=True,
        )


def print_plan(plan: MatrixPlan) -> None:
    """Print the number of candidate, legal, selected, and grouped runs."""
    print("Matrix plan", flush=True)
    print(f"  candidate runs: {plan.candidates}", flush=True)
    print(f"  legal runs:     {plan.legal}", flush=True)
    print(f"  selected runs:  {plan.selected}", flush=True)
    print(f"  configs:        {len(plan.jobs)}", flush=True)
    print(f"  test cases:     {len(plan.tests)}", flush=True)


@dataclass
class _TestTotals:
    counts: Counter[MatrixStatus] = field(default_factory=Counter)
    real_time_s: float = 0.0
    sim_time_ns: float = 0.0


def _result_summary(plan: MatrixPlan) -> dict[str, _TestTotals]:
    totals: defaultdict[str, _TestTotals] = defaultdict(_TestTotals)
    for job in plan.jobs:
        for result in job.results:
            current = totals[result.fullname]
            current.counts[result.status] += 1
            current.real_time_s += result.real_time_s
            current.sim_time_ns += result.sim_time_ns
    return dict(totals)


def print_summary(plan: MatrixPlan, elapsed: float) -> None:
    """Print aggregated test results and details for failed configurations."""
    totals = _result_summary(plan)
    names = [test.fullname for test in plan.tests]
    name_width = max([len("TEST")] + [len(name) for name in names])
    separator = "*" * (name_width + 75)
    print(separator)
    print(
        f"** {'TEST':<{name_width}}  PASS  FAIL  ERROR  SKIP  TOTAL  "
        f"SIM TIME (ns)  REAL TIME (s) **"
    )
    print(separator)
    for name in names:
        current = totals.get(name, _TestTotals())
        counts = current.counts
        total = sum(counts.values())
        print(
            f"** {name:<{name_width}}  {counts[MatrixStatus.PASS]:>4}  "
            f"{counts[MatrixStatus.FAIL]:>4}  {counts[MatrixStatus.ERROR]:>5}  "
            f"{counts[MatrixStatus.SKIP]:>4}  {total:>5}  "
            f"{current.sim_time_ns:>13.2f}  {current.real_time_s:>13.2f} **"
        )
    print(separator)
    config_counts = Counter(job.status for job in plan.jobs)
    print(
        f"** CONFIGS={len(plan.jobs)} PASS={config_counts[MatrixStatus.PASS]} "
        f"FAIL={config_counts[MatrixStatus.FAIL]} "
        f"ERROR={config_counts[MatrixStatus.ERROR]} "
        f"SKIP={config_counts[MatrixStatus.SKIP]} RUNS={plan.test_executions} "
        f"TOTAL TIME={elapsed:.2f}s **"
    )
    print(separator)

    failed = [
        job
        for job in plan.jobs
        if job.status not in {MatrixStatus.PASS, MatrixStatus.SKIP}
    ]
    if failed:
        print("\nFailed matrix configurations:")
        for job in failed:
            failed_tests = ", ".join(
                result.fullname
                for result in job.results
                if result.status in {MatrixStatus.FAIL, MatrixStatus.ERROR}
            )
            print(f"  {job.config_id}: {failed_tests or ', '.join(job.tests)}")
            for name, value in job.config.to_runtime_dict().items():
                print(f"    {name}={value}")
            if job.log_path:
                print(f"    log: {job.log_path}")


def write_results(project_root: Path, plan: MatrixPlan) -> Path:
    """Write the compact, ordered matrix result manifest."""
    configurations = [
        {
            "id": job.config_id,
            "status": job.status.value,
            "log": job.log_path,
            "sim_time_ns": sum(result.sim_time_ns for result in job.results),
            "real_time_s": sum(result.real_time_s for result in job.results),
            "config": job.config.to_runtime_dict(),
        }
        for job in plan.jobs
    ]

    path = project_root / "logs" / "matrix-results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(configurations, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path
