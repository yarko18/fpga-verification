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

# Video implementation reference

Recommended reading order:

1. `src/fpga_verification/video/core.py`: vendor-independent `FrameSize` and
   `compare_frames`.
2. `src/fpga_verification/altera/video/format.py`: `VideoFormat`,
   `ImageGenerator`, and Avalon-ST `VideoPayloadCodec`.
3. `src/fpga_verification/altera/video/packets.py`: Altera
   Avalon-ST Video user, control, and video packet wire format.
4. `src/fpga_verification/altera/video/codec.py`: conversion
   between neutral frames and VIP packets.
5. `src/fpga_verification/altera/video/checker.py`:
   control-before-video checks and active frame-size validation.
6. `src/fpga_verification/altera/video/uvm/agent.py`: pyuvm source, monitor,
   sink, sequence, and item classes for VIP packet streams.
7. `src/fpga_verification/sim/scoreboards/analysis.py`: shared `AnalysisImp`
   helper that forwards pyuvm analysis writes to a Python callable.
8. `src/fpga_verification/altera/video/uvm/scoreboard.py`: strict ordered
   protocol scoreboard used underneath IP-specific behavior models.
9. `src/fpga_verification/sim/agents/frame_source.py`: output-only conduit
   source contract and pre-drive `FrameTransaction` publication.
10. `tests/test_video.py`, `tests/test_altera_video.py`, and
   `tests/test_altera_video_agent.py`: fast regression tests that do not require
   Questa.

The package is installed as one dependency set. A normal install provides the
neutral video helpers, protocol codecs, cocotb simulation utilities, pyuvm
agents, and HIL helpers together:

```powershell
python -m pip install -e .
```

For early experiments, change `width`, `height`, color planes, and
`pixels_in_parallel` in small unit tests first. Run the fast Python tests
before moving the same scenario into a cocotb or Questa regression. See
[Video frames](guide/video-frames.md) for the public data API and
[Altera Avalon-ST Video](guide/altera-video.md) for packet conversion.
