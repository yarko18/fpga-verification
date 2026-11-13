# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from pathlib import Path

from fpga_verification.sim.runners import run_rtl_test


PROJECT_ROOT = Path(__file__).resolve().parent


def main():
    run_rtl_test(
        project_root=PROJECT_ROOT,
        sources=("../src",),
        hdl_toplevel="adder",
        test_module="test",
        parameters={"DATA_WIDTH": 8},
    )


if __name__ == "__main__":
    main()
