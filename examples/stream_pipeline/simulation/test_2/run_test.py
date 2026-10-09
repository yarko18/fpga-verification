# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

from pathlib import Path
import sys

from fpga_verification.altera.quartus import run_rtl_test


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if __package__:
    from .config import get_test_config
else:
    sys.path.insert(0, str(PROJECT_ROOT))
    from simulation.test_2.config import get_test_config


def main():
    run_rtl_test(
        project_root=PROJECT_ROOT,
        source_dirs=("rtl",),
        hdl_toplevel="stream_pipeline",
        test_module="simulation.test_2.test",
        config=get_test_config(),
        intel_libraries=("altera_mf",),
    )


if __name__ == "__main__":
    main()
