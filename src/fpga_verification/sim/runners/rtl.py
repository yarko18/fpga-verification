# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5
#
# Unless explicitly acquired and licensed from Licensor under another license,
# the contents of this file are subject to the Reciprocal Public License ("RPL")
# Version 1.5, or subsequent versions as allowed by the RPL, and You may not copy
# or use this file in either source code or executable form, except in compliance
# with the terms and conditions of the RPL.
#
# All software distributed under the RPL is provided strictly on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, AND LICENSOR
# HEREBY DISCLAIMS ALL SUCH WARRANTIES, INCLUDING WITHOUT LIMITATION, ANY
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, QUIET
# ENJOYMENT, OR NON-INFRINGEMENT. See the RPL for specific language governing
# rights and limitations under the RPL.

import os
from pathlib import Path

from ._common import (
    DEFAULT_SIMULATOR,
    prepare_test_run,
    resolve_path,
    resolve_test_config,
)
from ._intel_simulation import prepare_intel_libraries


def _check_results(results_xml):
    from cocotb_tools.runner import get_results

    num_tests, num_failed = get_results(results_xml)
    if num_failed:
        raise SystemExit(f"Cocotb failed {num_failed} of {num_tests} tests")


def _discover_sources(project_root, source_dirs):
    sources = []
    seen = set()

    for source_dir in source_dirs:
        source_dir = resolve_path(project_root, source_dir)
        if not source_dir.is_dir():
            raise FileNotFoundError(f"RTL source directory does not exist: {source_dir}")

        discovered = sorted(
            source
            for source in source_dir.rglob("*")
            if source.is_file() and source.suffix.lower() in {".v", ".sv"}
        )
        for source in discovered:
            key = source.resolve()
            if key not in seen:
                seen.add(key)
                sources.append(source)

    return sources


def rtl_test_cocotb(
    project_root,
    hdl_toplevel,
    test_module,
    sources=None,
    source_dirs=("src",),
    intel_libraries=(),
    quartus_sim_lib=None,
    apply_simulation_fixes=True,
    parameters=None,
    debug=False,
    compile_log=None,
    build_args=None,
    test_args=None,
    extra_env=None,
):
    """Compile plain RTL plus optional Intel models and run a cocotb test."""
    from cocotb_tools.runner import get_runner

    project_root = Path(project_root)
    sim = os.getenv("SIM", DEFAULT_SIMULATOR)

    build_dir = project_root / f"sim_build_{sim}"

    if sources is None:
        sources = _discover_sources(project_root, source_dirs)
    else:
        sources = [Path(source) for source in sources]

    vendor_sources = prepare_intel_libraries(
        intel_libraries,
        project_root=project_root,
        quartus_sim_lib=quartus_sim_lib,
        simulator=sim,
        output_dir=project_root / "logs" / "simulation_models",
        apply_simulation_fixes=apply_simulation_fixes,
    )
    sources = vendor_sources + sources

    runner = get_runner(sim)

    default_build_args = []

    if sim == "verilator":
        default_build_args += [
            "-Wno-fatal",
            "--timescale", "1ns/1ps",
            "-CFLAGS", "-std=c++20",
        ]

    if sim == "questa":
        default_build_args += [
            "-timescale", "1ns/1ps",
        ]

    build_args = default_build_args + list(build_args or ())

    if parameters is None:
        parameters = {}
    parameters = {
        name: int(value) if isinstance(value, bool) else value
        for name, value in parameters.items()
    }

    build_kwargs = {}
    if compile_log is not None:
        compile_log = Path(compile_log)
        compile_log.parent.mkdir(parents=True, exist_ok=True)
        print(f"{sim} compile log: {compile_log}", flush=True)
        build_kwargs["log_file"] = compile_log
    else:
        print("RTL sources:")
        for s in sources:
            print("  ", s)

    runner.build(
        sources=sources,
        hdl_toplevel=hdl_toplevel,
        build_dir=build_dir,
        always=True,
        waves=debug,
        build_args=build_args,
        parameters=parameters,
        **build_kwargs,
    )

    default_test_args = []

    if sim == "questa":
        enable_acc = debug or os.getenv("QUESTA_ACC", "0").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if enable_acc:
            default_test_args += ["-voptargs=+acc"]
        else:
            default_test_args += ["-no_autoacc"]

    if debug and sim == "questa":
        default_test_args += ["-do", "wave.do"]

    test_args = default_test_args + list(test_args or ())

    results_xml = runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
        hdl_toplevel_lang="verilog",
        build_dir=build_dir,
        gui=debug if sim == "questa" else False,
        waves=debug,
        test_args=test_args,
        extra_env=extra_env,
    )
    _check_results(results_xml)


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
    """Run a standard RTL cocotb simulation from a script or pytest.

    ``intel_libraries`` contains simulator-independent logical names. Their
    models are loaded from ``quartus_sim_lib`` (or a discovered Quartus
    installation) and compiled before all project RTL.
    """
    project_root = Path(project_root)
    debug, sim = prepare_test_run(
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
        compile_log=project_root / "logs" / f"{sim}_compile.log",
        parameters=parameters,
        extra_env=extra_env,
        **kwargs,
    )
