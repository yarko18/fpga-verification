# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

import os
from pathlib import Path

from fpga_verification.altera.quartus.component import (
    prepare_component_simulation,
)

from ._common import (
    DEFAULT_SIMULATOR,
    _parse_run_args,
    prepare_test_run,
    resolve_test_config,
)
from .rtl import _rtl_test_cocotb


def _component_build_args(simulator, build_args):
    """Return caller arguments plus safe simulator defaults for Intel IP."""
    build_args = list(build_args or ())
    if simulator == "verilator" and "-Wno-PARAMNODEFAULT" not in build_args:
        build_args.insert(0, "-Wno-PARAMNODEFAULT")
    return build_args


def _component_test_cocotb(*, build_args=None, **kwargs):
    """Prepare an Altera component and execute the internal RTL backend."""
    simulator = os.getenv("SIM", DEFAULT_SIMULATOR)
    return prepare_component_simulation(
        rtl_backend=_rtl_test_cocotb,
        simulator=simulator,
        build_args=_component_build_args(
            simulator,
            build_args,
        ),
        **kwargs,
    )


def run_component_test(
    *,
    project_root,
    component_file,
    hdl_toplevel,
    test_module,
    config=None,
    component_parameters=None,
    derived_parameters=None,
    sources=("../../src", "../../../common"),
    project_directory="../../..",
    test_module_env=None,
    python_paths=("..", "../../../common"),
    debug=None,
    argv=None,
    generate_only=False,
    retain_generated=False,
    clean_build=True,
    enable_questa_acc=False,
    artifacts_root=None,
    **kwargs,
):
    """Run a generated Altera component through the common RTL backend.

    ``derived_parameters`` may be a mapping or a callable receiving the final
    resolved ``config``. Use it for lower-level HDL parameters calculated from
    independent configuration fields; do not duplicate those values in the
    ``ComponentConfig`` dataclass.
    """
    project_root = Path(project_root)
    if test_module_env is not None:
        test_module = os.getenv(test_module_env, test_module)

    run_args = _parse_run_args(argv)
    if run_args.plan and not run_args.matrix:
        raise ValueError("--plan requires --matrix")
    if run_args.matrix:
        if generate_only:
            raise ValueError("generate_only cannot be combined with --matrix")
        if debug is True or run_args.debug:
            raise ValueError("GUI/debug mode cannot be combined with --matrix")
        prepare_test_run(
            project_root=project_root,
            python_paths=python_paths,
            debug=False,
            argv=(),
            clean_build=False,
            enable_questa_acc=enable_questa_acc,
        )
        from fpga_verification.sim.matrix import run_matrix

        return run_matrix(
            project_root=project_root,
            baseline=config,
            test_module=test_module,
            test_patterns=run_args.matrix_tests,
            plan_only=run_args.plan,
        )

    from fpga_verification.sim.matrix import (
        matrix_artifact_root,
        resolve_matrix_config,
    )

    config = resolve_matrix_config(config)
    artifacts_root = (
        matrix_artifact_root(project_root)
        if artifacts_root is None
        else Path(artifacts_root)
    )
    debug, sim = prepare_test_run(
        project_root=project_root,
        artifacts_root=artifacts_root,
        python_paths=python_paths,
        debug=debug,
        argv=argv,
        clean_build=clean_build,
        enable_questa_acc=enable_questa_acc,
    )

    component_parameters, extra_env = resolve_test_config(
        config,
        parameters=component_parameters,
        extra_env=kwargs.pop("extra_env", None),
    )
    if component_parameters is None:
        component_parameters = {}
    if derived_parameters is not None:
        resolved_derived = (
            derived_parameters(config)
            if callable(derived_parameters)
            else derived_parameters
        )
        resolved_derived = dict(resolved_derived)
        overlap = set(component_parameters) & set(resolved_derived)
        if overlap:
            raise ValueError(
                "derived_parameters may not override independent HDL parameters: "
                + ", ".join(sorted(overlap))
            )
        component_parameters.update(resolved_derived)
    if extra_env is not None:
        kwargs["extra_env"] = extra_env

    log_dir = artifacts_root / "logs"

    return _component_test_cocotb(
        project_root=project_root,
        component_file=component_file,
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
        sources=sources,
        component_parameters=component_parameters,
        project_directory=project_directory,
        debug=debug,
        generate_only=generate_only,
        ip_generate_log=log_dir / "ip_generate.log",
        compile_log=log_dir / f"{sim}_compile.log",
        retain_generated=retain_generated,
        artifacts_root=artifacts_root,
        **kwargs,
    )
