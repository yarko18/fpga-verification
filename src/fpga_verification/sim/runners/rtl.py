# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

import os
from pathlib import Path

from ._common import (
    DEFAULT_SIMULATOR,
    _parse_run_args,
    prepare_test_run,
    resolve_path,
    resolve_test_config,
)
from ._source_order import order_sources


_RTL_SUFFIXES = {".v", ".sv"}


def _check_results(results_xml):
    from cocotb_tools.runner import get_results

    num_tests, num_failed = get_results(results_xml)
    if num_failed:
        raise SystemExit(f"Cocotb failed {num_failed} of {num_tests} tests")


def _expand_sources(project_root, entries):
    sources = []
    seen = set()
    contains_directory = False

    for entry in entries:
        entry = resolve_path(project_root, entry)
        if not entry.exists():
            raise FileNotFoundError(f"RTL source path does not exist: {entry}")

        if entry.is_dir():
            contains_directory = True
            discovered = sorted(
                source
                for source in entry.rglob("*")
                if source.is_file() and source.suffix.lower() in _RTL_SUFFIXES
            )
        elif entry.is_file() and entry.suffix.lower() in _RTL_SUFFIXES:
            discovered = (entry,)
        else:
            raise ValueError(f"RTL source must be a .v/.sv file or directory: {entry}")

        for source in discovered:
            key = source.resolve()
            if key not in seen:
                seen.add(key)
                sources.append(source)

    return sources, contains_directory


def discover_sources(project_root, sources):
    sources, _ = _expand_sources(project_root, sources)
    return sources


def prepare_sources(
    project_root,
    *,
    sources=("src",),
    includes=(),
    defines=None,
):
    """Expand mixed source paths and order directory-based source sets."""
    expanded, contains_directory = _expand_sources(project_root, sources)

    # Preserve the historical meaning of an explicit file-only list: its order
    # is authoritative. Directory discovery needs dependency ordering because
    # lexical filesystem order is not a valid SystemVerilog compilation order.
    if contains_directory:
        return order_sources(
            expanded,
            include_dirs=includes,
            defines=defines,
        )
    return expanded


def _rtl_test_cocotb(
    project_root,
    hdl_toplevel,
    test_module,
    sources=("src",),
    intel_libraries=(),
    quartus_sim_lib=None,
    apply_simulation_fixes=True,
    parameters=None,
    includes=(),
    defines=None,
    debug=False,
    compile_log=None,
    build_args=None,
    test_args=None,
    extra_env=None,
    build_dir=None,
):
    """Compile RTL with optional prepared Intel models and run cocotb."""
    from cocotb_tools.runner import get_runner

    project_root = Path(project_root)
    sim = os.getenv("SIM", DEFAULT_SIMULATOR)

    if build_dir is None:
        build_dir = project_root / f"sim_build_{sim}"
    else:
        build_dir = Path(build_dir)

    includes = [resolve_path(project_root, path) for path in includes]
    sources = prepare_sources(
        project_root,
        sources=sources,
        includes=includes,
        defines=defines,
    )
    vendor_sources = []
    if intel_libraries:
        from fpga_verification.altera.quartus.simulation import (
            prepare_intel_libraries,
        )

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
        includes=includes,
        defines=dict(defines or {}),
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
    sources=("src",),
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
    """Run RTL with optional prepared Intel simulation libraries."""
    if _parse_run_args(argv).matrix:
        raise NotImplementedError(
            "parameter matrix execution is currently supported by run_component_test()"
        )
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

    return _rtl_test_cocotb(
        project_root=project_root,
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
        sources=sources,
        intel_libraries=intel_libraries,
        quartus_sim_lib=quartus_sim_lib,
        apply_simulation_fixes=apply_simulation_fixes,
        debug=debug,
        compile_log=project_root / "logs" / f"{sim}_compile.log",
        parameters=parameters,
        extra_env=extra_env,
        **kwargs,
    )
