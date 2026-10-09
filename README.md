<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5

Unless explicitly acquired and licensed from Licensor under another license,
the contents of this file are subject to the Reciprocal Public License ("RPL")
Version 1.5, or subsequent versions as allowed by the RPL, and You may not copy
or use this file in either source code or executable form, except in compliance
with the terms and conditions of the RPL.

All software distributed under the RPL is provided strictly on an "AS IS"
basis, WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, AND LICENSOR
HEREBY DISCLAIMS ALL SUCH WARRANTIES, INCLUDING WITHOUT LIMITATION, ANY
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, QUIET
ENJOYMENT, OR NON-INFRINGEMENT. See the RPL for specific language governing
rights and limitations under the RPL.
-->

# FPGA Verification

Reusable Python tools for FPGA simulation and hardware-in-the-loop
verification. The library combines protocol codecs, cocotb and pyuvm
components, Intel simulation runners, DMA modeling, performance measurements,
and Quartus System Console access.

[Documentation](https://yarko18.github.io/fpga-verification/) ·
[PyPI](https://pypi.org/project/fpga-verification/) ·
[Video endianness example](examples/stream_pipeline) ·
[Changelog](CHANGELOG.md)

## Install

Python 3.10 through 3.13 is supported.

```bash
python -m pip install fpga-verification
```

For local library development, install a checkout from the repository root in
editable mode:

```bash
python -m pip install -e ".[docs]"
```

## What is included

- Avalon-ST and Avalon-MM cocotb helpers;
- Intel Avalon-ST Video packets, codecs, agents, and scoreboards;
- runners for plain RTL, Intel components, and Platform Designer systems;
- an Intel streaming DMA model and sparse byte memory;
- packet latency and throughput analysis;
- persistent Intel System Console access for hardware tests;
- video frame and raw numeric data helpers.

Start with the [documentation](https://yarko18.github.io/fpga-verification/)
or run the [video-packet endianness example](examples/stream_pipeline). It
preserves CONTROL and USER packets while reversing byte order in VIDEO payload
beats. The repository includes examples for several verification patterns. The
site separates a complete tutorial, verification concepts, focused how-to
guides, case studies, and generated API reference.

## Build the documentation locally

```bash
./docs/mkdoc.sh setup
./docs/mkdoc.sh serve
./docs/mkdoc.sh build
```

GitHub Pages is rebuilt automatically when documentation changes reach
`main`.
