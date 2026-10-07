# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

from pathlib import Path

from examples.stream_pipeline.simulation.vip.config import get_test_config
from fpga_verification.sim.runners import run_rtl_test


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]
    run_rtl_test(
        project_root=project_root,
        source_dirs=("rtl",),
        python_paths=(".", "../.."),
        hdl_toplevel="stream_pipeline_fifo",
        test_module="examples.stream_pipeline.simulation.vip.test_pyuvm",
        config=get_test_config(),
        intel_libraries=("altera_mf",),
    )
