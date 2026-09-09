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
class TestConfig(ComponentConfig):
    width: int = hdl_parameter(64, name="WIDTH")
    enable: bool = hdl_parameter(True, name="ENABLE")
    label: str = "smoke"


def test_component_config_has_separate_hdl_and_runtime_representations():
    config = TestConfig(width=80, label="matrix")

    assert config.to_parameters() == {"WIDTH": 80, "ENABLE": True}
    assert config.to_runtime_dict() == {"width": 80, "enable": True, "label": "matrix"}


def test_runtime_configuration_json_round_trip():
    config = TestConfig(width=80, label="matrix")

    loaded = load_runtime_config(TestConfig, runtime_config_environment(config))

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
        load_runtime_config(TestConfig, environment)
