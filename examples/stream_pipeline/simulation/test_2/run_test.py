# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from pathlib import Path
import sys

from fpga_verification.altera.quartus import run_rtl_test

PROJECT_ROOT = Path(__file__).resolve().parent

from .config import get_test_config

def main():
    run_rtl_test(
        project_root=PROJECT_ROOT,
        sources=("../../rtl",),
        hdl_toplevel="stream_pipeline",
        test_module="simulation.test_2.test",
        config=get_test_config(),
        intel_libraries=("altera_mf",),
        python_paths=("../..",),
    )


if __name__ == "__main__":
    main()
