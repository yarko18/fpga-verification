# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from pathlib import Path

from fpga_verification.sim.runners import run_rtl_test

from config import get_test_config


PROJECT_ROOT = Path(__file__).resolve().parent


def main():
    run_rtl_test(
        project_root=PROJECT_ROOT,
        sources=("../src",),
        hdl_toplevel="stream_fifo",
        test_module="simulation.test",
        config=get_test_config(),
        intel_libraries=("altera_mf",),
        python_paths=("..",),
    )


if __name__ == "__main__":
    main()
