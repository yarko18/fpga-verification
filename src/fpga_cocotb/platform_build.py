# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

def compile_with_msim_setup(project_root, hdl_toplevel):
    import subprocess
    from pathlib import Path

    project_root = Path(project_root)

    qsys_simdir = (
        project_root
        / hdl_toplevel
        / hdl_toplevel
        / "testbench"
    )

    build_dir = project_root / "sim_build"
    build_dir.mkdir(exist_ok=True)

    do_file = build_dir / "compile_ip.do"

    do_file.write_text(f"""
set QSYS_SIMDIR "{qsys_simdir.as_posix()}"
set TOP_LEVEL_NAME {hdl_toplevel}

source "$QSYS_SIMDIR/mentor/msim_setup.tcl"

dev_com
com

quit -f
""")

    subprocess.run(
        ["vsim", "-c", "-do", str(do_file)],
        cwd=build_dir,
        check=True,
    )

def get_msim_libraries(msim_setup_path):
    import re
    from pathlib import Path

    text = Path(msim_setup_path).read_text()

    libs = []

    # Ищем все "-work library_name"
    for lib in re.findall(r"-work\s+([A-Za-z0-9_]+)", text):
        if lib not in libs:
            libs.append(lib)

    return libs

def run_questa(project_root, hdl_toplevel, test_module, debug=False):
    import os
    from pathlib import Path
    from cocotb_tools.runner import get_runner

    project_root = Path(project_root)
    build_dir = project_root / "sim_build"

    os.environ["COCOTB_LOG_LEVEL"] = "INFO"

    compile_with_msim_setup(project_root, hdl_toplevel)

    runner = get_runner("questa")

    msim_setup = (
        project_root
        / hdl_toplevel
        / hdl_toplevel
        / "testbench"
        / "mentor"
        / "msim_setup.tcl"
    )

    libs = get_msim_libraries(msim_setup)

    test_args = ["-voptargs=+acc"]

    for lib in libs:
        test_args += ["-L", lib]

    if debug:
        test_args += ["-do", "wave.do"]

    runner.build(
        sources=[],
        hdl_toplevel=hdl_toplevel,
        build_dir=build_dir,
        always=False,
    )

    runner.test(
        hdl_toplevel=hdl_toplevel,
        hdl_toplevel_library=f"{hdl_toplevel}_inst",
        test_module=test_module,
        hdl_toplevel_lang="verilog",
        build_dir=build_dir,
        gui=debug,
        waves=debug,
        test_args=test_args,
    )
    
def run_verilator(project_root, hdl_toplevel, test_module, debug=False):
    from pathlib import Path
    from cocotb_tools.runner import get_runner

    project_root = Path(project_root)
    build_dir = project_root / "sim_build_verilator"

    sim_dir = (
        project_root
        / hdl_toplevel
        / hdl_toplevel
        / "testbench"
        / f"{hdl_toplevel}_tb"
        / "simulation"
    )

    sub = sim_dir / "submodules"
    mentor_src = sub / "mentor" / "src_hdl"

    sources = []

    # packages first
    sources += [
        sub / "verbosity_pkg.sv",
        sub / "avalon_utilities_pkg.sv",
    ]

    # regular generated RTL
    sources += sorted(sub.glob("*.v"))
    sources += sorted(sub.glob("*.sv"))

    # Intel VIP nested sources
    sources += sorted(mentor_src.glob("*.v"))
    sources += sorted(mentor_src.glob("*.sv"))

    # remove duplicates and put platform1.v last
    unique = []
    seen = set()

    for s in sources:
        if s.name == f"{hdl_toplevel}.v":
            continue
        if s not in seen:
            unique.append(s)
            seen.add(s)

    unique.append(sub / f"{hdl_toplevel}.v")
    sources = unique

    print("Verilator sources:")
    for s in sources:
        print("  ", s)

    runner = get_runner("verilator")

    runner.build(
        sources=sources,
        hdl_toplevel=hdl_toplevel,
        build_dir=build_dir,
        always=True,
        build_args=[
            "-Wno-fatal",
            "--timescale", "1ps/1ps",
            "-CFLAGS", "-std=c++20",
            "-I" + str(sub),
            "-I" + str(mentor_src),
        ],
    )

    runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
        hdl_toplevel_lang="verilog",
        build_dir=build_dir,
        waves=debug,
    )

def platform_test_cocotb(
        project_root,
        hdl_toplevel,
        test_module,
        debug=False):
    import os

    sim = os.getenv("SIM", "questa")

    if sim == "verilator":
        run_verilator(project_root, hdl_toplevel, test_module, debug)
    elif sim == "questa":
        run_questa(project_root, hdl_toplevel, test_module, debug)
    else:
        raise ValueError(f"Unsupported SIM={sim}")
    
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
    sim = os.getenv("SIM", "verilator")

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

    runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
        hdl_toplevel_lang="verilog",
        build_dir=build_dir,
        gui=debug if sim == "questa" else False,
        waves=debug,
        test_args=test_args,
    )
