# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import hashlib
import argparse
import os
import sys
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from contextlib import nullcontext
from pathlib import Path

from .rtl import rtl_test_cocotb


def _resolve_path(project_root, path):
    path = Path(path)
    return path if path.is_absolute() else Path(project_root) / path


def _hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def _original_source_index(project_root, source_dirs):
    originals = {}

    for source_dir in source_dirs:
        source_dir = _resolve_path(project_root, source_dir)
        for extension in ("*.v", "*.sv"):
            for source in sorted(source_dir.rglob(extension)):
                originals.setdefault(_hash_file(source), source)

    return originals


def _spd_hdl_sources(spd_path):
    simulation_dir = Path(spd_path).parent
    root = ET.parse(spd_path).getroot()
    return [
        simulation_dir / entry.attrib["path"]
        for entry in root.findall("file")
        if Path(entry.attrib["path"]).suffix.lower() in {".v", ".sv"}
    ]


def _use_original_sources(project_root, source_dirs, generated_sources):
    originals = _original_source_index(project_root, source_dirs)
    sources = []
    retained_generated = []
    seen_sources = set()

    for generated in generated_sources:
        source = originals.get(_hash_file(generated), generated)
        if source != generated:
            generated.unlink()
        else:
            retained_generated.append(generated)

        key = source.resolve()
        if key not in seen_sources:
            seen_sources.add(key)
            sources.append(source)

    return sources, retained_generated


def _quartus_sim_sources(ip_generate, model_files):
    if not model_files:
        return []

    quartus_root = Path(ip_generate).resolve().parents[2]
    sim_lib = quartus_root / "eda" / "sim_lib"
    sources = [sim_lib / file_name for file_name in model_files]
    missing = [source for source in sources if not source.exists()]

    if missing:
        raise FileNotFoundError(f"Missing Quartus simulation model: {missing[0]}")

    return sources


def _remove_empty_directories(root):
    for directory in sorted(Path(root).rglob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def _clean_directory(path):
    path = Path(path)
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    path.mkdir(parents=True)


def _run_command(command, cwd, log_path=None, append_log=False):
    if log_path is None:
        subprocess.run(command, cwd=cwd, check=True)
        return

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append_log else "w"

    with log_path.open(mode, encoding="utf-8", errors="replace") as log:
        print("Command:", " ".join(str(item) for item in command), file=log)
        print(file=log)
        log.flush()
        try:
            subprocess.run(
                command,
                cwd=cwd,
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except subprocess.CalledProcessError:
            print(f"Command failed, see {log_path}", flush=True)
            raise


def _make_ipx(project_root, source_dirs, output_dir, log_path=None, append_log=False):
    if not source_dirs:
        return None

    ip_make_ipx = shutil.which("ip-make-ipx") or shutil.which("ip-make-ipx.exe")
    if ip_make_ipx is None:
        raise FileNotFoundError("ip-make-ipx is not available on PATH")

    ipx_path = Path(output_dir) / "components.ipx"
    source_directory = ",".join(
        str(_resolve_path(project_root, source_dir))
        for source_dir in source_dirs
    )

    _run_command(
        [
            ip_make_ipx,
            "--thorough-descent",
            f"--source-directory={source_directory}",
            f"--output={ipx_path}",
        ],
        cwd=project_root,
        log_path=log_path,
        append_log=append_log,
    )

    return ipx_path


def intel_component_test_cocotb(
    project_root,
    component_file,
    hdl_toplevel,
    test_module,
    source_dirs=(),
    component_parameters=None,
    project_directory=None,
    part=None,
    quartus_model_files=("220model.v", "altera_mf.v"),
    debug=False,
    generate_only=False,
    ip_generate_log=None,
    compile_log=None,
    retain_generated=False,
    make_ipx=True,
    ipx_source_dirs=None,
    ip_search_paths=(),
):
    """Generate an Intel component composition and simulate against original RTL.

    Generated HDL files that are byte-identical to source files in ``source_dirs``
    are replaced by those source paths before invoking ``rtl_test_cocotb``. Any
    remaining generated HDL implements Platform Designer composition wiring. By
    default it exists only for this call; with ``generate_only=True`` its
    directory is retained and returned for inspection. By default a temporary
    Platform Designer IP index is generated from ``source_dirs`` and passed to
    ``ip-generate`` as a search path.
    """
    project_root = Path(project_root)
    component_file = _resolve_path(project_root, component_file)
    if project_directory is None:
        project_directory = project_root
    else:
        project_directory = _resolve_path(project_root, project_directory)

    ip_generate = shutil.which("ip-generate")
    if ip_generate is None:
        raise FileNotFoundError("ip-generate is not available on PATH")

    if component_parameters is None:
        component_parameters = {}

    keep_generated = generate_only or retain_generated

    if keep_generated:
        fixed_output_dir = project_root / f".ip_generate_{hdl_toplevel}"
        _clean_directory(fixed_output_dir)
        generation_context = nullcontext(fixed_output_dir)
    else:
        generation_context = tempfile.TemporaryDirectory(
            prefix=f".ip_generate_{hdl_toplevel}_",
            dir=project_root,
        )

    with generation_context as temporary_dir:
        output_dir = Path(temporary_dir)
        spd_path = output_dir / f"{hdl_toplevel}.spd"
        (output_dir / "submodules").mkdir()

        log_has_content = False
        if ip_generate_log is not None:
            ip_generate_log = Path(ip_generate_log)
            print(f"IP generation log: {ip_generate_log}", flush=True)

        resolved_ip_search_paths = [
            _resolve_path(project_root, path)
            for path in ip_search_paths
        ]

        if make_ipx:
            ipx_path = _make_ipx(
                project_root,
                source_dirs if ipx_source_dirs is None else ipx_source_dirs,
                output_dir,
                log_path=ip_generate_log,
                append_log=log_has_content,
            )
            log_has_content = ipx_path is not None or log_has_content
            if ipx_path is not None:
                resolved_ip_search_paths.insert(0, ipx_path)

        command = [
            ip_generate,
            f"--component-file={component_file}",
            f"--project-directory={project_directory}",
            f"--output-directory={output_dir}",
            "--file-set=SIM_VERILOG",
            f"--output-name={hdl_toplevel}",
            "--remove-qsys-generate-warning",
            f"--report-file=spd:{spd_path}",
        ]
        if part is not None:
            command.append(f"--part={part}")

        if resolved_ip_search_paths:
            search_path = ",".join(str(path) for path in resolved_ip_search_paths)
            command.append(f"--search-path={search_path},$")

        command.extend(
            f"--component-parameter={name}={value}"
            for name, value in component_parameters.items()
        )

        _run_command(
            command,
            cwd=project_root,
            log_path=ip_generate_log,
            append_log=log_has_content,
        )

        generated_sources = _spd_hdl_sources(spd_path)
        spd_path.unlink()
        sources, retained_generated = _use_original_sources(
            project_root,
            source_dirs,
            generated_sources,
        )
        _remove_empty_directories(output_dir)
        sources = _quartus_sim_sources(ip_generate, quartus_model_files) + sources

        lifecycle = "Retained" if keep_generated else "Temporary"
        generated_hdl_lines = [f"{lifecycle} generated composition HDL:"]
        generated_hdl_lines.extend(f"   {source}" for source in retained_generated)
        if keep_generated:
            generated_hdl_lines.append(f"Generated output directory: {output_dir}")

        if ip_generate_log is None:
            for line in generated_hdl_lines:
                print(line)
        else:
            with ip_generate_log.open(
                "a", encoding="utf-8", errors="replace"
            ) as log:
                print(file=log)
                for line in generated_hdl_lines:
                    print(line, file=log)

        if generate_only:
            print("Generated output directory:", output_dir, flush=True)
            return output_dir

        rtl_test_cocotb(
            project_root=project_root,
            hdl_toplevel=hdl_toplevel,
            test_module=test_module,
            sources=sources,
            debug=debug,
            compile_log=compile_log,
        )


def _prepend_python_paths(paths):
    path_strings = [str(Path(path)) for path in paths]

    for path in reversed(path_strings):
        if path not in sys.path:
            sys.path.insert(0, path)

    pythonpath = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = os.pathsep.join(
        path_strings + ([pythonpath] if pythonpath else [])
    )


def _clean_sim_build(project_root, sim):
    build_dir = Path(project_root) / f"sim_build_{sim}"
    preserved_files = {}
    for relative_path in ("wave.do",):
        file_path = build_dir / relative_path
        if file_path.is_file():
            preserved_files[relative_path] = file_path.read_bytes()

    if build_dir.exists():
        shutil.rmtree(build_dir)

    for relative_path, content in preserved_files.items():
        file_path = build_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)


def _parse_run_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run an Intel component cocotb simulation.",
        add_help=False,
    )
    parser.add_argument(
        "-g",
        dest="debug",
        action="store_true",
        help="run simulator in GUI/debug mode",
    )
    return parser.parse_args(sys.argv[1:] if argv is None else list(argv))


def run_intel_component_test(
    *,
    project_root,
    component_file,
    hdl_toplevel,
    test_module,
    config=None,
    component_parameters=None,
    source_dirs=("../../src", "../../../common"),
    project_directory="../../..",
    test_module_env=None,
    python_paths=("..", "../../../common"),
    debug=None,
    generate_only=False,
    retain_generated=False,
    clean_build=True,
    enable_questa_acc=False,
    **kwargs,
):
    """Run a standard Intel component cocotb simulation from a small script."""
    project_root = Path(project_root)

    os.environ.setdefault("COCOTB_ANSI_OUTPUT", "1")
    os.environ.pop("NO_COLOR", None)
    if enable_questa_acc:
        os.environ.setdefault("QUESTA_ACC", "1")

    args = _parse_run_args()
    if debug is None:
        debug = args.debug

    if component_parameters is None:
        if config is None:
            component_parameters = {}
        elif hasattr(config, "to_parameters"):
            component_parameters = config.to_parameters()
        else:
            component_parameters = dict(config)

    _prepend_python_paths(
        _resolve_path(project_root, path)
        for path in python_paths
    )

    sim = os.getenv("SIM", "questa")
    log_dir = project_root / "logs"

    if clean_build:
        _clean_sim_build(project_root, sim)

    if test_module_env is not None:
        test_module = os.getenv(test_module_env, test_module)

    intel_component_test_cocotb(
        project_root=project_root,
        component_file=component_file,
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
        source_dirs=source_dirs,
        component_parameters=component_parameters,
        project_directory=project_directory,
        debug=debug,
        generate_only=generate_only,
        ip_generate_log=log_dir / "ip_generate.log",
        compile_log=log_dir / f"{sim}_compile.log",
        retain_generated=retain_generated,
        **kwargs,
    )