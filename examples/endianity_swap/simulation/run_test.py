# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from pathlib import Path

from fpga_verification.sim.runners import run_rtl_test

from config import get_test_config


PROJECT_ROOT = Path(__file__).resolve().parent


def main():
    run_rtl_test(
        project_root=PROJECT_ROOT,
        sources=("../rtl",),
        hdl_toplevel="endianity_swap",
        test_module="simulation.test",
        config=get_test_config(),
        python_paths=("..",),
    )


if __name__ == "__main__":
    main()
