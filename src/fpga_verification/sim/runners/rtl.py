# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path


DEFAULT_SIMULATOR = "verilator"


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
    )
    _check_results(results_xml)
