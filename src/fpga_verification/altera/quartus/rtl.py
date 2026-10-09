# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

"""Plain RTL simulation with optional Quartus library models."""

import os
from pathlib import Path

from fpga_verification.sim.runners import rtl as generic_rtl
from fpga_verification.sim.runners._common import (
    prepare_test_run,
    resolve_test_config,
)

from .simulation import prepare_intel_libraries


def rtl_test_cocotb(
    project_root,
    hdl_toplevel,
    test_module,
    sources=None,
    source_dirs=("src",),
    intel_libraries=(),
    quartus_sim_lib=None,
    apply_simulation_fixes=True,
    **kwargs,
):
    """Compile RTL plus requested Quartus library models and run cocotb."""

    project_root = Path(project_root)
    if sources is None:
        sources = generic_rtl.discover_sources(project_root, source_dirs)
    else:
        sources = [Path(source) for source in sources]

    simulator = os.getenv("SIM", generic_rtl.DEFAULT_SIMULATOR)
    vendor_sources = prepare_intel_libraries(
        intel_libraries,
        project_root=project_root,
        quartus_sim_lib=quartus_sim_lib,
        simulator=simulator,
        output_dir=project_root / "logs" / "simulation_models",
        apply_simulation_fixes=apply_simulation_fixes,
    )

    return generic_rtl.rtl_test_cocotb(
        project_root=project_root,
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
        sources=vendor_sources + sources,
        **kwargs,
    )


def run_rtl_test(
    *,
    project_root,
    hdl_toplevel,
    test_module,
    config=None,
    parameters=None,
    extra_env=None,
    source_dirs=("src",),
    intel_libraries=(),
    quartus_sim_lib=None,
    apply_simulation_fixes=True,
    python_paths=(".",),
    debug=None,
    argv=None,
    clean_build=True,
    enable_questa_acc=False,
    test_module_env=None,
    **kwargs,
):
    """Run an RTL cocotb test with optional Quartus simulation libraries."""

    project_root = Path(project_root)
    debug, simulator = prepare_test_run(
        project_root=project_root,
        python_paths=python_paths,
        debug=debug,
        argv=argv,
        clean_build=clean_build,
        enable_questa_acc=enable_questa_acc,
    )

    if test_module_env is not None:
        test_module = os.getenv(test_module_env, test_module)

    parameters, extra_env = resolve_test_config(
        config,
        parameters=parameters,
        extra_env=extra_env,
    )

    return rtl_test_cocotb(
        project_root=project_root,
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
        source_dirs=source_dirs,
        intel_libraries=intel_libraries,
        quartus_sim_lib=quartus_sim_lib,
        apply_simulation_fixes=apply_simulation_fixes,
        debug=debug,
        compile_log=project_root / "logs" / f"{simulator}_compile.log",
        parameters=parameters,
        extra_env=extra_env,
        **kwargs,
    )
