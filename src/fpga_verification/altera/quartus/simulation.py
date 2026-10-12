# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Resolve simulator-independent Altera library names to simulation models."""

import os
import shutil
from pathlib import Path

from fpga_verification.sim.runners._common import resolve_path

from ._simulation_fixes import prepare_simulation_models


_INTEL_LIBRARY_FILES = {
    "lpm": "220model.v",
    "altera_mf": "altera_mf.v",
    "altera_lnsim": "altera_lnsim.sv",
    "altera_primitives": "altera_primitives.v",
}


def _validate_sim_lib(path, *, source):
    path = Path(path).expanduser()
    if not path.is_dir():
        raise FileNotFoundError(
            f"Quartus simulation library directory from {source} does not exist: {path}"
        )
    return path.resolve()


def _sim_lib_from_installation(path):
    """Find ``eda/sim_lib`` above a Quartus executable, including symlinks."""
    executable = Path(path).expanduser().resolve()
    for directory in executable.parents:
        candidate = directory / "eda" / "sim_lib"
        if candidate.is_dir():
            return candidate.resolve()
    return None


def resolve_quartus_sim_lib(project_root, quartus_sim_lib=None):
    """Resolve an explicit, configured, or PATH-discovered Quartus model tree."""
    if quartus_sim_lib is not None:
        return _validate_sim_lib(
            resolve_path(project_root, quartus_sim_lib),
            source="quartus_sim_lib",
        )

    configured_sim_lib = os.getenv("QUARTUS_SIM_LIB")
    if configured_sim_lib:
        return _validate_sim_lib(configured_sim_lib, source="QUARTUS_SIM_LIB")

    quartus_root = os.getenv("QUARTUS_ROOTDIR")
    if quartus_root:
        return _validate_sim_lib(
            Path(quartus_root) / "eda" / "sim_lib",
            source="QUARTUS_ROOTDIR",
        )

    for executable_name in ("quartus_sh", "ip-generate"):
        executable = shutil.which(executable_name)
        if executable is not None:
            candidate = _sim_lib_from_installation(executable)
            if candidate is not None:
                return candidate

    raise FileNotFoundError(
        "Quartus simulation libraries were requested but eda/sim_lib could not "
        "be found; pass quartus_sim_lib, set QUARTUS_SIM_LIB or QUARTUS_ROOTDIR, "
        "or add Quartus tools to PATH"
    )


def prepare_intel_libraries(
    libraries,
    *,
    project_root,
    quartus_sim_lib,
    simulator,
    output_dir,
    apply_simulation_fixes=True,
):
    """Return requested Altera models in caller order, ready for compilation."""
    if libraries is None:
        return []
    if isinstance(libraries, str):
        raise TypeError("intel_libraries must be a sequence of library names")

    library_names = list(dict.fromkeys(libraries))
    if not library_names:
        return []

    unknown = [name for name in library_names if name not in _INTEL_LIBRARY_FILES]
    if unknown:
        supported = ", ".join(sorted(_INTEL_LIBRARY_FILES))
        raise ValueError(
            f"Unknown Altera simulation library {unknown[0]!r}; supported libraries: "
            f"{supported}"
        )

    sim_lib = resolve_quartus_sim_lib(project_root, quartus_sim_lib)
    sources = [sim_lib / _INTEL_LIBRARY_FILES[name] for name in library_names]
    missing = [source for source in sources if not source.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing Quartus simulation model: {missing[0]}")

    return prepare_simulation_models(
        sources,
        simulator=simulator,
        output_dir=output_dir,
        enabled=apply_simulation_fixes,
    )
