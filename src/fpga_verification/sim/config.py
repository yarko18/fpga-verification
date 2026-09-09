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

"""Configuration contract shared by Platform Designer and cocotb tests."""

from __future__ import annotations

import json
import os
from dataclasses import MISSING, asdict, fields
from typing import Any, Mapping


RUNTIME_CONFIG_ENV = "FPGA_VERIFICATION_TEST_CONFIG_JSON"
"""Environment variable containing the resolved test configuration JSON."""


def hdl_parameter(default: Any = MISSING, *, name: str | None = None, **kwargs):
    """Declare a dataclass field which is also a Platform Designer parameter.

    ``name`` defaults to the dataclass field name.  All fields remain present in
    the runtime configuration; the metadata only controls ``to_parameters()``.
    """
    from dataclasses import field

    metadata = dict(kwargs.pop("metadata", {}))
    metadata["fpga_verification.hdl_parameter"] = name or True
    if default is MISSING:
        return field(metadata=metadata, **kwargs)
    return field(default=default, metadata=metadata, **kwargs)


class ComponentConfig:
    """Mixin for a resolved component configuration dataclass.

    A configuration has two deliberately different representations: Platform
    Designer receives only HDL parameters, while cocotb receives the complete,
    already-resolved configuration.  Runtime loading is strict so a stale test
    cannot silently run with defaults different from the generated DUT.
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

        try:
            return cls(**dict(value))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid {cls.__name__} runtime configuration values") from error


def runtime_config_environment(config: ComponentConfig) -> dict[str, str]:
    """Return the cocotb environment payload for an already-resolved config."""
    if not isinstance(config, ComponentConfig):
        raise TypeError("Runtime config must inherit ComponentConfig")
    return {RUNTIME_CONFIG_ENV: json.dumps(config.to_runtime_dict(), sort_keys=True)}


def load_runtime_config(config_type, environ: Mapping[str, str] | None = None):
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
