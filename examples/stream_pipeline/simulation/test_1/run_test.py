# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from pathlib import Path
import sys

from fpga_verification.sim.runners import run_rtl_test


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if __package__:
    from .config import get_test_config
else:
    # A file executed directly has no package context, so make this example's
    # package importable without depending on the caller's working directory.
    sys.path.insert(0, str(PROJECT_ROOT))
    from simulation.test_1.config import get_test_config


def main():
    cfg = get_test_config()
    run_rtl_test(
        project_root=PROJECT_ROOT,
        source_dirs=("rtl",),
        hdl_toplevel="stream_pipeline",
        test_module="simulation.test_1.test",
        config=cfg,
    )


if __name__ == "__main__":
    main()
