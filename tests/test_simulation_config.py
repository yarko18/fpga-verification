# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from dataclasses import dataclass

import pytest

from fpga_verification.sim import (
    ComponentConfig,
    RUNTIME_CONFIG_ENV,
    hdl_parameter,
    load_runtime_config,
)
from fpga_verification.sim.config import runtime_config_environment


@dataclass
class _TestConfig(ComponentConfig):
    width: int = hdl_parameter(64, name="WIDTH")
    enable: bool = hdl_parameter(True, name="ENABLE")
    label: str = "smoke"


def test_component_config_has_separate_hdl_and_runtime_representations():
    config = _TestConfig(width=80, label="matrix")

    assert config.to_parameters() == {"WIDTH": 80, "ENABLE": True}
    assert config.to_runtime_dict() == {"width": 80, "enable": True, "label": "matrix"}


def test_runtime_configuration_json_round_trip():
    config = _TestConfig(width=80, label="matrix")

    loaded = load_runtime_config(_TestConfig, runtime_config_environment(config))

    assert loaded == config


@pytest.mark.parametrize(
    "environment, error",
    [
        ({}, RuntimeError),
        ({RUNTIME_CONFIG_ENV: "not json"}, ValueError),
        ({RUNTIME_CONFIG_ENV: "[]"}, TypeError),
        ({RUNTIME_CONFIG_ENV: '{"width": 64, "enable": true}'}, ValueError),
        ({RUNTIME_CONFIG_ENV: '{"width": 64, "enable": true, "label": "x", "other": 1}'}, ValueError),
    ],
)
def test_runtime_configuration_rejects_missing_malformed_and_unknown_values(environment, error):
    with pytest.raises(error):
        load_runtime_config(_TestConfig, environment)


@pytest.mark.parametrize(
    "payload",
    [
        '{"width": "64", "enable": true, "label": "x"}',
        '{"width": 64, "enable": 1, "label": "x"}',
        '{"width": 64, "enable": true, "label": 1}',
    ],
)
def test_runtime_configuration_rejects_wrong_json_field_types(payload):
    with pytest.raises(ValueError, match="runtime configuration value"):
        load_runtime_config(_TestConfig, {RUNTIME_CONFIG_ENV: payload})


def test_runtime_configuration_rejects_wrong_in_memory_field_types():
    config = _TestConfig(width="64")

    with pytest.raises(ValueError, match="runtime configuration value"):
        config.to_runtime_dict()
