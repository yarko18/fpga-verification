# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Configuration contract shared by HDL builds and cocotb tests."""

from __future__ import annotations

import json
import os
from dataclasses import MISSING, asdict, fields
from types import UnionType
from typing import (
    Any,
    Callable,
    Literal,
    Mapping,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)


CONFIG_CASE_ENV = "FPGA_VERIFICATION_CONFIG_CASE"
"""Environment variable selecting a host-side named configuration case."""

RUNTIME_CONFIG_ENV = "FPGA_VERIFICATION_TEST_CONFIG_JSON"
"""Environment variable containing the resolved test configuration JSON."""

_ConfigT = TypeVar("_ConfigT")

MATRIX_VALUES_METADATA = "fpga_verification.matrix_values"
"""Dataclass metadata key containing an optional matrix domain."""


def _parameter_field(default, *, values=None, metadata=None, **kwargs):
    from dataclasses import field

    metadata = dict(metadata or {})
    if values is not None:
        values = tuple(values)
        if not values:
            raise ValueError("matrix parameter values must not be empty")
        metadata[MATRIX_VALUES_METADATA] = values
    if default is MISSING:
        return field(metadata=metadata, **kwargs)
    return field(default=default, metadata=metadata, **kwargs)


def hdl_parameter(
    default: Any = MISSING,
    *,
    name: str | None = None,
    values=None,
    **kwargs,
):
    """Declare a dataclass field which is also an HDL build parameter.

    ``name`` defaults to the dataclass field name.  All fields remain present in
    the runtime configuration; the HDL metadata only controls
    ``to_parameters()``. ``values`` is an optional matrix domain. Ordinary tests
    do not need to declare it; it is required only when a matrix test chooses
    this field in its ``vary`` list.

    Declare independent public parameters here. Parameters derived from other
    configuration values belong at the component/runner boundary, not in the
    configuration dataclass.
    """
    metadata = dict(kwargs.pop("metadata", {}))
    metadata["fpga_verification.hdl_parameter"] = name or True
    return _parameter_field(
        default,
        values=values,
        metadata=metadata,
        **kwargs,
    )


def matrix_parameter(default: Any = MISSING, *, values=None, **kwargs):
    """Declare a runtime-only configuration field with an optional matrix domain.

    Use this for an independent test/build choice that is not passed directly as
    an HDL parameter. As with :func:`hdl_parameter`, ``values`` remains optional
    until a matrix test varies the field.
    """
    return _parameter_field(default, values=values, **kwargs)


class ComponentConfig:
    """Mixin for a resolved component configuration dataclass.

    A configuration has two deliberately different representations: the HDL
    build receives only marked parameters, while cocotb receives the complete,
    already-resolved configuration. Runtime loading is strict so a stale test
    cannot silently run with defaults different from the compiled DUT.

    Keep only independent public choices in the dataclass. HDL values derived
    from those choices are resolved by the component or runner and must not
    become duplicate configuration fields.
    """

    def to_parameters(self) -> dict[str, Any]:
        parameters = {}
        for item in fields(self):
            name = item.metadata.get("fpga_verification.hdl_parameter")
            if name:
                parameters[item.name if name is True else name] = getattr(self, item.name)
        return parameters

    def to_runtime_dict(self) -> dict[str, Any]:
        value = asdict(self)
        _validate_runtime_mapping(type(self), value)
        try:
            json.dumps(value)
        except (TypeError, ValueError) as error:
            raise TypeError("ComponentConfig runtime values must be JSON serializable") from error
        return value

    @classmethod
    def from_runtime_dict(cls, value: Mapping[str, Any]):
        if not isinstance(value, Mapping):
            raise TypeError(f"{cls.__name__} runtime configuration must be a JSON object")

        expected = {item.name for item in fields(cls)}
        actual = set(value)
        missing = expected - actual
        extra = actual - expected
        if missing or extra:
            messages = []
            if missing:
                messages.append(f"missing fields: {', '.join(sorted(missing))}")
            if extra:
                messages.append(f"unknown fields: {', '.join(sorted(extra))}")
            raise ValueError(f"Invalid {cls.__name__} runtime configuration ({'; '.join(messages)})")

        _validate_runtime_mapping(cls, value)

        try:
            return cls(**dict(value))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid {cls.__name__} runtime configuration values") from error


def _validate_runtime_mapping(config_type, value: Mapping[str, Any]) -> None:
    type_hints = get_type_hints(config_type)
    for item in fields(config_type):
        annotation = type_hints.get(item.name, Any)
        if not _matches_runtime_type(value[item.name], annotation):
            raise ValueError(
                f"Invalid {config_type.__name__} runtime configuration value for "
                f"{item.name!r}: expected {annotation!r}"
            )


def _matches_runtime_type(value: Any, annotation: Any) -> bool:
    """Validate the JSON types used by a resolved component configuration."""
    if annotation is Any:
        return True

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in (Union, UnionType):
        return any(_matches_runtime_type(value, item) for item in arguments)
    if origin is Literal:
        return value in arguments and any(type(value) is type(item) for item in arguments)
    if origin is list:
        return isinstance(value, list) and (
            not arguments
            or all(_matches_runtime_type(item, arguments[0]) for item in value)
        )
    if origin is dict:
        key_type, value_type = arguments or (Any, Any)
        return isinstance(value, dict) and all(
            _matches_runtime_type(key, key_type)
            and _matches_runtime_type(item, value_type)
            for key, item in value.items()
        )

    if annotation in (bool, int, float, str):
        return type(value) is annotation
    if annotation is type(None):
        return value is None
    try:
        return isinstance(value, annotation)
    except TypeError:
        return True


def runtime_config_environment(config: ComponentConfig) -> dict[str, str]:
    """Return the cocotb environment payload for an already-resolved config."""
    if not isinstance(config, ComponentConfig):
        raise TypeError("Runtime config must inherit ComponentConfig")
    return {RUNTIME_CONFIG_ENV: json.dumps(config.to_runtime_dict(), sort_keys=True)}


def resolve_config_case(
    cases: Mapping[str, _ConfigT | Callable[[], _ConfigT]],
    case: str | None = None,
    *,
    default: str = "default",
    environ: Mapping[str, str] | None = None,
    label: str = "configuration",
) -> _ConfigT:
    """Resolve one host-side named configuration case.

    Values may be pre-built configurations or zero-argument factories. Factories
    keep unselected cases lazy, so validation is limited to the selected case.
    """
    environ = os.environ if environ is None else environ
    selected_name = environ.get(CONFIG_CASE_ENV, default) if case is None else case

    try:
        selected = cases[selected_name]
    except KeyError as error:
        available = ", ".join(cases)
        raise ValueError(
            f"Unknown {label} case {selected_name!r}; available: {available}"
        ) from error

    return selected() if callable(selected) else selected


def load_test_config(config_type, environ: Mapping[str, str] | None = None):
    """Strictly restore ``config_type`` from runner-provided JSON.

    Missing variables, malformed JSON and both missing and unknown fields are
    errors.  Tests must never fall back to constructing a default config.
    """
    if not issubclass(config_type, ComponentConfig):
        raise TypeError("config_type must inherit ComponentConfig")

    environ = os.environ if environ is None else environ
    try:
        payload = environ[RUNTIME_CONFIG_ENV]
    except KeyError as error:
        raise RuntimeError(
            f"{RUNTIME_CONFIG_ENV} is required; run the test via the FPGA verification runner"
        ) from error

    try:
        value = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"{RUNTIME_CONFIG_ENV} must contain a JSON object") from error
    return config_type.from_runtime_dict(value)
