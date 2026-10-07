# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

from pathlib import Path

import pytest

from fpga_verification.sim.runners import _intel_simulation


def test_quartus_sim_lib_can_be_discovered_from_quartus_on_path(tmp_path, monkeypatch):
    quartus_root = tmp_path / "quartus"
    executable = quartus_root / "bin" / "quartus_sh"
    sim_lib = quartus_root / "eda" / "sim_lib"
    executable.parent.mkdir(parents=True)
    executable.touch()
    sim_lib.mkdir(parents=True)

    monkeypatch.delenv("QUARTUS_SIM_LIB", raising=False)
    monkeypatch.delenv("QUARTUS_ROOTDIR", raising=False)
    monkeypatch.setattr(
        _intel_simulation.shutil,
        "which",
        lambda name: str(executable) if name == "quartus_sh" else None,
    )

    assert _intel_simulation.resolve_quartus_sim_lib(tmp_path) == sim_lib.resolve()


def test_quartus_sim_lib_environment_avoids_machine_path_in_runner(tmp_path, monkeypatch):
    sim_lib = tmp_path / "eda" / "sim_lib"
    sim_lib.mkdir(parents=True)
    monkeypatch.setenv("QUARTUS_SIM_LIB", str(sim_lib))

    assert _intel_simulation.resolve_quartus_sim_lib(Path("unused")) == sim_lib.resolve()


def test_unknown_intel_library_fails_with_supported_names(tmp_path):
    with pytest.raises(ValueError, match="Unknown Intel simulation library.*altera_mf"):
        _intel_simulation.prepare_intel_libraries(
            ("unknown",),
            project_root=tmp_path,
            quartus_sim_lib=None,
            simulator="verilator",
            output_dir=tmp_path / "models",
        )


def test_intel_library_argument_is_not_a_single_string(tmp_path):
    with pytest.raises(TypeError, match="sequence"):
        _intel_simulation.prepare_intel_libraries(
            "altera_mf",
            project_root=tmp_path,
            quartus_sim_lib=None,
            simulator="verilator",
            output_dir=tmp_path / "models",
        )
