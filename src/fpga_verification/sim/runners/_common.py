# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from fnmatch import translate
from pathlib import Path

from ..._version import __version__
from ..config import ComponentConfig, _print_selected_parameter_preset

DEFAULT_SIMULATOR = "verilator"
_DISTRIBUTION_NAME = "fpga-verification"
_AUTHOR = "Yaroslav Mariukha"


def _print_runner_banner():
    print(
        f"{_DISTRIBUTION_NAME} {__version__} | by {_AUTHOR}",
        flush=True,
    )


def resolve_path(project_root, path):
    path = Path(path)
    return path if path.is_absolute() else Path(project_root) / path


def resolve_test_config(config, parameters=None, extra_env=None):
    """Resolve one config into matching HDL parameters and cocotb state."""
    if config is None:
        return parameters, extra_env

    from ..config import ComponentConfig, runtime_config_environment

    if not isinstance(config, ComponentConfig):
        raise TypeError("config must inherit ComponentConfig")

    resolved_parameters = config.to_parameters()
    if parameters is not None and dict(parameters) != resolved_parameters:
        raise ValueError("parameters must match the resolved ComponentConfig")

    config_environment = runtime_config_environment(config)
    resolved_environment = dict(extra_env or {})
    overlap = set(resolved_environment) & set(config_environment)
    if overlap:
        raise ValueError(
            "extra_env may not override resolved config: "
            + ", ".join(sorted(overlap))
        )
    resolved_environment.update(config_environment)
    return resolved_parameters, resolved_environment


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


@dataclass(frozen=True)
class RunArguments:
    """Runner options shared by RTL and generated-component entry points."""

    debug: bool
    coverage: bool
    matrix: bool
    plan: bool
    test_patterns: tuple[str, ...]
    param_preset: str | None
    jobs: int


class _RunnerArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(
            f"{message}. Use --help to see available runner options."
        )


def _is_pytest_passthrough(arguments):
    """Recognize pytest's common quiet/verbose invocation plus test path."""
    pytest_flags = {"-q", "-v", "-x", "-s"}
    has_test_path = False
    for argument in arguments:
        if argument in pytest_flags:
            continue
        if not argument.startswith("-") and argument.endswith(".py"):
            has_test_path = True
            continue
        return False
    return has_test_path


def _test_filter_from_patterns(patterns) -> str | None:
    """Translate runner globs into a cocotb full-name filter."""
    expressions = []
    for pattern in patterns:
        expression = translate(pattern)
        expressions.extend((f"^{expression}", rf"(?:^|\.){expression}"))
    if not expressions:
        return None
    return "(?:" + "|".join(expressions) + ")"


def resolve_parameter_config(config, parameter_presets, selected_preset):
    """Resolve the runner's direct config or one named parameter preset."""
    if parameter_presets is None:
        if selected_preset is not None:
            raise ValueError(
                "--param-preset requires parameter_presets in run_test.py"
            )
        return config
    if config is not None:
        raise ValueError("config and parameter_presets cannot be used together")
    if "default" not in parameter_presets:
        raise ValueError("parameter_presets must define a 'default' preset")

    preset_name = "default" if selected_preset is None else selected_preset
    try:
        preset = parameter_presets[preset_name]
    except KeyError as error:
        available = ", ".join(parameter_presets)
        raise ValueError(
            f"Unknown parameter preset {preset_name!r}; available: {available}"
        ) from error

    resolved = preset() if callable(preset) else preset
    if not isinstance(resolved, ComponentConfig):
        raise TypeError("parameter preset must resolve to a ComponentConfig")
    if selected_preset is not None:
        _print_selected_parameter_preset(
            preset_name,
            resolved,
        )
    return resolved


def _available_cpu_count() -> int:
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def _parse_jobs(value: str) -> int:
    max_cpu = _available_cpu_count()
    if value == "max":
        return max_cpu
    try:
        jobs = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "jobs must be a positive integer or 'max'"
        ) from error
    if jobs <= 0:
        raise argparse.ArgumentTypeError("jobs must be a positive integer or 'max'")
    if jobs > max_cpu:
        raise argparse.ArgumentTypeError(f"only {max_cpu} threads are available but {jobs} were given")
    return jobs


def _parse_run_args(argv=None) -> RunArguments:
    parser = _RunnerArgumentParser(
        description="Run a cocotb simulation.",
    )
    parser.add_argument(
        "-g",
        dest="debug",
        action="store_true",
        help="run simulator in GUI/debug mode",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="enable functional coverage declared by the simulator tests",
    )
    parser.add_argument(
        "--matrix",
        action="store_true",
        help="run the parameter matrix declared by cocotb/pyuvm tests",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="print the matrix plan without compiling or simulating",
    )
    parser.add_argument(
        "--test",
        dest="test_patterns",
        action="append",
        default=[],
        metavar="PATTERN",
        help="run matching cocotb/pyuvm tests (repeatable glob pattern)",
    )
    parser.add_argument(
        "--param-preset",
        metavar="NAME",
        help="select a named HDL/test parameter preset",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=_parse_jobs,
        default=None,
        metavar="N|max",
        help="run up to N matrix configurations concurrently (default: 1)",
    )
    arguments = sys.argv[1:] if argv is None else list(argv)
    args, unknown = parser.parse_known_args(arguments)
    running_under_pytest = argv is None and "pytest" in sys.modules
    if unknown and not (
        running_under_pytest or _is_pytest_passthrough(unknown)
    ):
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")
    if args.plan and not args.matrix:
        raise ValueError("--plan requires --matrix")
    if args.param_preset is not None and args.matrix:
        raise ValueError("--param-preset cannot be combined with --matrix")
    if args.jobs is not None and not args.matrix:
        raise ValueError("--jobs requires --matrix")
    return RunArguments(
        debug=args.debug,
        coverage=args.coverage,
        matrix=args.matrix,
        plan=args.plan,
        test_patterns=tuple(args.test_patterns),
        param_preset=args.param_preset,
        jobs=1 if args.jobs is None else args.jobs,
    )


def prepare_test_run(
    *,
    project_root,
    artifacts_root=None,
    python_paths=(),
    debug=None,
    argv=None,
    clean_build=True,
    enable_questa_acc=False,
):
    project_root = Path(project_root)
    artifacts_root = project_root if artifacts_root is None else Path(artifacts_root)
    _print_runner_banner()

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
        _clean_sim_build(artifacts_root, sim)

    return debug, sim
