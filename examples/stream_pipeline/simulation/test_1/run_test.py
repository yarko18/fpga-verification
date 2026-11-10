# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from pathlib import Path
import sys

from fpga_verification.sim.runners import run_rtl_test

from config import get_test_config

sources = (
    "../../rtl",
)

def main():
    
    run_rtl_test(
        project_root=Path(__file__).resolve().parent,
        sources=sources,
        hdl_toplevel="stream_pipeline",
        test_module="simulation.test_1.test",
        config=get_test_config(),
        python_paths=("../..",),
    )


if __name__ == "__main__":
    main()
