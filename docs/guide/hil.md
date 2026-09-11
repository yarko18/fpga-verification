<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Hardware-in-the-loop

`IntelSystemConsoleSession` keeps one Quartus `system-console` process alive
for repeated memory transfers and JTAG UART commands. This avoids paying tool
startup cost for every operation.

```python
from fpga_verification.hil.intel import IntelSystemConsoleSession

with IntelSystemConsoleSession(
    master_index=0,
    uart_index=0,
    work_dir=".",
) as hw:
    hw.write_memory(frame, address=input_address)
    response = hw.command("g\n")
    result = hw.read_memory(frame.shape, address=output_address)
```

Memory data is transferred as little-endian 16-bit words. UART commands are
UTF-8 text; the command protocol itself belongs to the software running on the
FPGA. The context manager closes the worker even when a test raises.

This API accesses real hardware. Confirm the selected service indices,
addresses, and buffer layout before writing. Use a dedicated `work_dir` when
sessions may run concurrently.

See the
[System Console notebook](https://github.com/yarko18/fpga-verification/blob/main/examples/07_hil_system_console.ipynb)
for lifecycle and failure handling.

Next: [the neutral video representation](video-frames.md).
