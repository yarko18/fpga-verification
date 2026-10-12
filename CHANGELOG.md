<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

# Changelog

## 1.1.1 - 2026-10-12

- Changed the project license for version 1.1.1 to the FPGA Verification
  Commercial Reciprocity License 1.0. Releases through 1.1.0 remain under
  their original licenses.
- Added dependency-ordered RTL source discovery. `run_rtl_test()` now accepts
  mixed `.v`/`.sv` files and recursively scanned directories in `sources`.
- Added a one-line project and author banner to runner logs.

## 1.1.0 - 2026-10-09

- Moved Altera-specific APIs under `fpga_verification.altera`, including
  Avalon-ST Video, Avalon-MM UVM components, DMA models, Quartus runners,
  Platform Designer, and System Console support.
- Split vendor-independent `FrameSize` and `compare_frames` from the Altera
  video format and payload codecs.
- Separated the vendor-independent RTL runner from the Quartus RTL wrapper;
  Quartus library selection now comes from `fpga_verification.altera.quartus`.
- Updated the stream-pipeline examples, documentation, and tests for the new
  public import structure.

## 1.0.6 - 2026-10-09

- Added recursive multi-directory RTL source discovery for relative and
  absolute paths.
- Added simulator-independent Intel library selection to the plain RTL runner,
  including Quartus model discovery and copied Verilator compatibility fixes.
- Added resolved `ComponentConfig` support to `run_rtl_test()` and an Intel
  `scfifo` example without requiring a component description or Platform
  Designer generation.
- Added Verilog-compatible encoding of boolean HDL parameters.
- Reworked the stream-pipeline example into two standalone cocotb testbenches
  around one parameterized RTL source: plain RTL and Intel `scfifo`.
- Added Linux and Windows wheel builds, including Python 3.12 artifacts for the
  `develop` branch and all supported Python versions for tagged releases.

## 1.0.5 - 2026-09-24

- Reorganized the documentation into getting-started material, guides, API
  reference, case studies, and a complete stream-pipeline tutorial.
- Added dedicated API documentation for Avalon-ST, Avalon-MM, and Intel DMA
  BFMs, including descriptors, address regions, and sparse memory behavior.
- Added guidance for verification contracts, DUT behavior models, testbench
  structure, agents, scoreboards, and simulation runners.
- Replaced the notebook examples with a runnable stream-pipeline RTL and pyuvm
  example, including model tests.
- Added dark and light themes, WaveDrom diagrams, inline Draw.io page export,
  and CI support for generated Draw.io SVG assets.

## 1.0.4 - 2026-09-15

- Create standard `VideoPacketPolicy` for intel video packets:
  - Use `EXACT` to compare frame shape and data,.
  - Use `SHAPE` to compare only output frame shape.
  - Use `DROP` if frame shouldn't exists on the output.

## 1.0.3 - 2026-09-15

- Added an optional default frame size to `ImageGenerator`.
- Expanded the simulation runner documentation and corrected the `run_rtl_test()` example.

## 1.0.2 - 2026-09-11

- Added the MkDocs Material documentation site, structured guides, and local
  documentation build helpers.
- Added automated documentation publication and restricted that workflow to
  relevant main-branch and pull-request changes.
- Replaced the former long-form README with a concise project entry point.

## 1.0.1 - 2026-09-10

- Preserved non-UTF-8 bytes while applying simulator-model source fixes.
- Pinned the tested cocotb and pyuvm versions and allowed the installed
  cocotbext-avalon package to provide its own compatible release.
- Restricted release CI to tags and added concurrency cancellation for
  superseded runs.
