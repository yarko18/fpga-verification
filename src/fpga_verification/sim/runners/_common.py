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

import argparse
import os
import shutil
import sys
from pathlib import Path

DEFAULT_SIMULATOR = "verilator"


def resolve_path(project_root, path):
    path = Path(path)
    return path if path.is_absolute() else Path(project_root) / path


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
        description="Run a cocotb simulation.",
        add_help=False,
    )
    parser.add_argument(
        "-g",
        dest="debug",
        action="store_true",
        help="run simulator in GUI/debug mode",
    )
    # A runner can also be called by pytest, whose arguments must not be
    # interpreted as errors by this small command-line compatibility layer.
    args, _ = parser.parse_known_args(sys.argv[1:] if argv is None else list(argv))
    return args


def prepare_test_run(
    *,
    project_root,
    python_paths=(),
    debug=None,
    argv=None,
    clean_build=True,
    enable_questa_acc=False,
):
    project_root = Path(project_root)

    os.environ.setdefault("COCOTB_ANSI_OUTPUT", "1")
    os.environ.pop("NO_COLOR", None)
    if enable_questa_acc:
        os.environ.setdefault("QUESTA_ACC", "1")

    if debug is None:
        debug = _parse_run_args(argv).debug

    if debug:
        print("Enable DEBUG mode", flush=True)

    _prepend_python_paths(
        resolve_path(project_root, path)
        for path in python_paths
    )

    sim = os.getenv("SIM", DEFAULT_SIMULATOR)
    if clean_build:
        _clean_sim_build(project_root, sim)

    return debug, sim
