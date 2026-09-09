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

from ._common import DEFAULT_SIMULATOR, prepare_test_run


def _check_results(results_xml):
    from cocotb_tools.runner import get_results

    num_tests, num_failed = get_results(results_xml)
    if num_failed:
        raise SystemExit(f"Cocotb failed {num_failed} of {num_tests} tests")


def rtl_test_cocotb(
    project_root,
    hdl_toplevel,
    test_module,
    sources=None,
    source_dirs=("src",),
    parameters=None,
    debug=False,
    compile_log=None,
    build_args=None,
    test_args=None,
    extra_env=None,
):
    from cocotb_tools.runner import get_runner

    project_root = Path(project_root)
    sim = os.getenv("SIM", DEFAULT_SIMULATOR)

    build_dir = project_root / f"sim_build_{sim}"

    if sources is None:
        sources = []

        for source_dir in source_dirs:
            src_dir = project_root / source_dir

            sources += sorted(src_dir.rglob("*.v"))
            sources += sorted(src_dir.rglob("*.sv"))

    sources = [Path(s) for s in sources]

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
    source_dirs=("src",),
    python_paths=(".",),
    debug=None,
    argv=None,
    clean_build=True,
    enable_questa_acc=False,
    test_module_env=None,
    **kwargs,
):
    """Run a standard RTL cocotb simulation from a script or pytest."""
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

    return rtl_test_cocotb(
        project_root=project_root,
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
        source_dirs=source_dirs,
        debug=debug,
        compile_log=project_root / "logs" / f"{sim}_compile.log",
        **kwargs,
    )
