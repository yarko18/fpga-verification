<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Simulation API

## Configuration

::: fpga_verification.sim.config
    options:
      show_root_heading: true
      members_order: source
      filters:
        - "!^_"

## Agents

::: fpga_verification.sim.agents
    options:
      show_root_heading: true
      members_order: source

## Scoreboards

::: fpga_verification.sim.scoreboards
    options:
      show_root_heading: true
      members_order: source

## Altera Avalon components

::: fpga_verification.altera.avalon
    options:
      show_root_heading: true
      members_order: source

## Altera Video UVM components

::: fpga_verification.altera.video.uvm
    options:
      show_root_heading: true
      members_order: source

## Performance metrics

::: fpga_verification.sim.stream_metrics
    options:
      show_root_heading: true
      members_order: source
      filters:
        - "!^_"
