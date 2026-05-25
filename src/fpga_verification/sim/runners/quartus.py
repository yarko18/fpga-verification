# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

def compile_with_msim_setup(project_root, hdl_toplevel):
    import subprocess
    from pathlib import Path

    project_root = Path(project_root)
    user_defined_elab_options = "-nocvg -voptargs=+acc -suppress 8630"

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
set USER_DEFINED_ELAB_OPTIONS "{user_defined_elab_options}"

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

def _read_text(path):
    from pathlib import Path

    return Path(path).read_text(errors="ignore")

def _platform_qsys_simdir(project_root, hdl_toplevel):
    from pathlib import Path

    return Path(project_root) / hdl_toplevel / hdl_toplevel / "testbench"

def _platform_msim_setup(project_root, hdl_toplevel):
    return _platform_qsys_simdir(project_root, hdl_toplevel) / "mentor" / "msim_setup.tcl"

def _msim_set_variables(msim_setup_path):
    import re

    variables = {}
    text = _read_text(msim_setup_path)

    for match in re.finditer(r'^\s*set\s+([A-Za-z0-9_]+)\s+(?:"([^"]*)"|(\S+))', text, re.MULTILINE):
        variables[match.group(1)] = match.group(2) if match.group(2) is not None else match.group(3)

    return variables

def _path_from_msim(value):
    import os
    import re
    from pathlib import Path

    value = value.replace("\\", "/")
    match = re.match(r"^([A-Za-z]):/(.*)$", value)

    if match and os.name != "nt":
        return Path("/mnt") / match.group(1).lower() / match.group(2)

    return Path(value)

def _project_drive_roots(project_root):
    from pathlib import Path

    project_root = Path(project_root)
    roots = []

    if project_root.anchor:
        roots.append(Path(project_root.anchor))

    parts = project_root.parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "mnt":
        roots.append(Path("/mnt") / parts[2])

    return list(dict.fromkeys(roots))

def _quartus_install_dir(project_root, msim_setup_path=None, msim_variables=None):
    import os

    for env_name in ("QUARTUS_INSTALL_DIR", "QUARTUS_ROOTDIR"):
        value = os.getenv(env_name)
        if value:
            path = _path_from_msim(value)
            if path.exists():
                return path

    if msim_variables is None and msim_setup_path is not None:
        msim_variables = _msim_set_variables(msim_setup_path)

    if msim_variables is not None and "QUARTUS_INSTALL_DIR" in msim_variables:
        path = _path_from_msim(msim_variables["QUARTUS_INSTALL_DIR"])
        if path.exists():
            return path

    for root in _project_drive_roots(project_root):
        intel_root = root / "intelFPGA"
        if not intel_root.exists():
            continue

        for version_dir in sorted(intel_root.iterdir(), reverse=True):
            quartus = version_dir / "quartus"
            if quartus.exists():
                return quartus

    return None

def _resolve_msim_source(raw_path, variables, base_dir):
    from pathlib import Path

    resolved = raw_path.replace("\\", "/")

    for name, value in variables.items():
        resolved = resolved.replace(f"${{{name}}}", value)
        resolved = resolved.replace(f"${name}", value)

    if "$" in resolved:
        return None

    path = _path_from_msim(resolved)

    if not path.is_absolute():
        path = Path(base_dir) / path

    return path

def _design_units(path):
    import re

    text = _read_text(path)
    return set(
        re.findall(
            r"^\s*(?:module|package|interface)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
            text,
            re.MULTILINE,
        )
    )

def _unique_verilator_sources(sources):
    unique = []
    seen_paths = set()
    seen_units = set()

    for source in sources:
        if source in seen_paths:
            continue

        units = _design_units(source)
        if units and units.issubset(seen_units):
            continue

        unique.append(source)
        seen_paths.add(source)
        seen_units.update(units)

    return unique

def _msim_verilog_sources(project_root, hdl_toplevel, include_testbench=False):
    import re

    qsys_simdir = _platform_qsys_simdir(project_root, hdl_toplevel)
    msim_setup = _platform_msim_setup(project_root, hdl_toplevel)

    if not msim_setup.exists():
        raise FileNotFoundError(msim_setup)

    variables = _msim_set_variables(msim_setup)
    variables["QSYS_SIMDIR"] = qsys_simdir.as_posix()

    quartus_install_dir = _quartus_install_dir(project_root, msim_setup, variables)
    if quartus_install_dir is not None:
        variables["QUARTUS_INSTALL_DIR"] = quartus_install_dir.as_posix()

    sources = []

    for line in _read_text(msim_setup).splitlines():
        if "vlog" not in line:
            continue

        for match in re.finditer(r'"([^"]+\.(?:sv|v))"', line):
            raw_path = match.group(1)
            source = _resolve_msim_source(raw_path, variables, msim_setup.parent)

            if source is None:
                continue

            if source.name.endswith("_ncrypt.v"):
                continue

            if not include_testbench and source.name == f"{hdl_toplevel}_tb.v":
                continue

            if source.exists():
                sources.append(source)

    return _unique_verilator_sources(sources)

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

    test_args = ["-nocvg", "-voptargs=+acc", "-suppress", "8630"]

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

    sources = _msim_verilog_sources(project_root, hdl_toplevel)
    include_dirs = list(dict.fromkeys(source.parent for source in sources))

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
            "-Wno-PARAMNODEFAULT",
            "--bbox-unsup",
            "--timescale", "1ps/1ps",
            "-CFLAGS", "-std=c++20",
            *["-I" + str(include_dir) for include_dir in include_dirs],
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
