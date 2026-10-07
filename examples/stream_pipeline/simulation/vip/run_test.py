# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

from pathlib import Path

from fpga_verification.sim.runners import run_rtl_test

from .config import get_test_config


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    cfg = get_test_config()
    run_rtl_test(
        project_root=project_root,
        source_dirs=("rtl",),
        hdl_toplevel="stream_pipeline",
        test_module="simulation.vip.test_pyuvm",
        config=cfg,
    )
