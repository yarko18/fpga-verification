<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: Apache-2.0
-->

## Где смотреть и что менять

Рекомендуемый порядок изучения:

1. `fpga_verification/video/core.py` — `FrameSize`, `VideoFormat`, `ImageGenerator`, `VideoPayloadCodec`.
2. `fpga_verification/protocols/avalon_st/intel_video/packets.py` — user/control/video packet wire format.
3. `fpga_verification/protocols/avalon_st/intel_video/codec.py` — frame ↔ VIP packets.
4. `fpga_verification/protocols/avalon_st/intel_video/checker.py` — control-before-video и проверка активного размера.
5. `fpga_verification/sim/agents/intel_video.py` — VIP pyuvm source/monitor/sink agent.
8. `linear-igc/simulation/core/test_env.py` — generator и отправка sequence в DUT.
9. `linear-igc/simulation/core/test_scoreboard.py` — monitor packets → frame → model comparison.

Для первых экспериментов меняйте `width`, `height`, planes и `pixels_in_parallel` в маленьких примерах notebook. После этого запускайте unit tests, и только затем cocotb/Questa regression.