# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import hashlib
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
):
    """Generate an Intel component composition and simulate against original RTL.

    Generated HDL files that are byte-identical to source files in ``source_dirs``
    are replaced by those source paths before invoking ``rtl_test_cocotb``. Any
    remaining generated HDL implements Platform Designer composition wiring. By
    default it exists only for this call; with ``generate_only=True`` its
    directory is retained and returned for inspection.
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
        generation_context = nullcontext(
            tempfile.mkdtemp(
                prefix=f".ip_generate_{hdl_toplevel}_",
                dir=project_root,
            )
        )
    else:
        generation_context = tempfile.TemporaryDirectory(
            prefix=f".ip_generate_{hdl_toplevel}_",
            dir=project_root,
        )

    with generation_context as temporary_dir:
        output_dir = Path(temporary_dir)
        spd_path = output_dir / f"{hdl_toplevel}.spd"
        (output_dir / "submodules").mkdir()

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
        command.extend(
            f"--component-parameter={name}={value}"
            for name, value in component_parameters.items()
        )

        if ip_generate_log is None:
            subprocess.run(command, cwd=project_root, check=True)
        else:
            ip_generate_log = Path(ip_generate_log)
            ip_generate_log.parent.mkdir(parents=True, exist_ok=True)
            print(f"IP generation log: {ip_generate_log}", flush=True)
            with ip_generate_log.open(
                "w", encoding="utf-8", errors="replace"
            ) as log:
                print(
                    "Command:",
                    " ".join(str(item) for item in command),
                    file=log,
                )
                print(file=log)
                log.flush()
                try:
                    subprocess.run(
                        command,
                        cwd=project_root,
                        check=True,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                except subprocess.CalledProcessError:
                    print(f"ip-generate failed, see {ip_generate_log}", flush=True)
                    raise

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
