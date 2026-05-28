# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

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
):
    import os
    from pathlib import Path
    from cocotb_tools.runner import get_runner

    project_root = Path(project_root)
    sim = os.getenv("SIM", "questa")

    build_dir = project_root / f"sim_build_{sim}"

    if sources is None:
        sources = []

        for source_dir in source_dirs:
            src_dir = project_root / source_dir

            sources += sorted(src_dir.rglob("*.v"))
            sources += sorted(src_dir.rglob("*.sv"))

    sources = [Path(s) for s in sources]

    print("RTL sources:")
    for s in sources:
        print("  ", s)

    runner = get_runner(sim)

    build_args = []

    if sim == "verilator":
        build_args += [
            "-Wno-fatal",
            "--timescale", "1ns/1ps",
            "-CFLAGS", "-std=c++20",
        ]

    if sim == "questa":
        build_args += [
            "-timescale", "1ns/1ps",
        ]

    if parameters is None:
        parameters = {}

    runner.build(
        sources=sources,
        hdl_toplevel=hdl_toplevel,
        build_dir=build_dir,
        always=True,
        build_args=build_args,
        parameters=parameters,
    )

    test_args = []

    if sim == "questa":
        test_args += ["-voptargs=+acc"]

    if debug and sim == "questa":
        test_args += ["-do", "wave.do"]

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
