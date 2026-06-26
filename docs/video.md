<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: Apache-2.0
-->

# Video Helpers Developer Notes

Recommended reading order:

1. `src/fpga_verification/video/core.py`: simulator-independent `FrameSize`,
   `VideoFormat`, `ImageGenerator`, `VideoPayloadCodec`, and `compare_frames`.
2. `src/fpga_verification/protocols/avalon_st/intel_video/packets.py`: Intel
   Avalon-ST Video user, control, and video packet wire format.
3. `src/fpga_verification/protocols/avalon_st/intel_video/codec.py`: conversion
   between neutral frames and VIP packets.
4. `src/fpga_verification/protocols/avalon_st/intel_video/checker.py`:
   control-before-video checks and active frame-size validation.
5. `src/fpga_verification/sim/agents/intel_video.py`: pyuvm source, monitor,
   sink, sequence, and item classes for VIP packet streams.
6. `tests/test_video.py`, `tests/test_intel_video.py`, and
   `tests/test_intel_video_agent.py`: fast regression tests that do not require
   Questa.

The package is installed as one dependency set. A normal install provides the
neutral video helpers, protocol codecs, cocotb simulation utilities, pyuvm
agents, and HIL helpers together:

```powershell
python -m pip install -e .
```

For early experiments, change `width`, `height`, color planes, and
`pixels_in_parallel` in small unit tests or notebooks first. Run the fast Python
tests before moving the same scenario into a cocotb or Questa regression.
