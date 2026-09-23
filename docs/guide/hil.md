<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

# Hardware-in-the-loop

`IntelSystemConsoleSession` keeps one Quartus `system-console` process alive
for repeated memory transfers and JTAG UART commands. It is suitable after a
simulation-level contract already exists: the same Python data and reference
model can then be used against a programmed board.

This API requires Quartus System Console, a programmed FPGA and matching
services in the design.

## Persistent session

The session starts one process and communicates with the packaged Tcl helper.
Reusing it avoids the startup overhead on every transfer. `JtagSession` remains
a backward-compatible alias.

```python
import numpy as np

from fpga_verification.hil.intel import IntelSystemConsoleSession

source = np.arange(64, dtype=np.uint16).reshape(8, 8)

with IntelSystemConsoleSession(
    system_console="system-console",
    master_index=0,
    uart_index=0,
    startup_timeout=30.0,
    work_dir=".",
) as hw:
    hw.write_memory(source, address=0x01000000)
    response = hw.command("status", timeout=3.0)
    observed = hw.read_memory(source.shape, address=0x01000000)

print(response)
print(observed.shape)
```

`master_index` and `uart_index` select services discovered by System Console.
`work_dir` contains temporary transfer files, so choose a dedicated writable
directory for concurrent sessions.

## Memory transfers

`write_memory(data, address, chunk_size=4096)` converts data to little-endian
unsigned 16-bit words and transfers it in chunks. `read_memory(shape, address,
chunk_size=4096)` returns a two-dimensional little-endian `uint16` array and
checks the received word count.

```python
def memory_round_trip(hw, source, address):
    hw.write_memory(source, address=address, chunk_size=16 * 1024)
    observed = hw.read_memory(
        source.shape, address=address, chunk_size=16 * 1024,
    )
    np.testing.assert_array_equal(observed, source.astype("<u2"))
    return observed
```

The current API is intentionally specialised to 16-bit two-dimensional data.
When transferring a video frame, first verify the plane order, geometry and
endianness against the hardware memory contract. The session cannot infer them.

## JTAG UART

`command(text, timeout=3.0, debug=False)` sends UTF-8 text and returns the
first non-empty response line. The board software defines the command protocol;
the library transports text only.

```python
def query_target(hw):
    version = hw.command("version", timeout=3.0)
    status = hw.command("status", timeout=3.0, debug=True)
    return version, status
```

Set `debug=True` only while diagnosing System Console/Tcl exchange; it prints
raw protocol lines.

## Lifecycle and safety

The context manager calls `open()` and guarantees `close()` after normal exit
or an exception. Manual use is available when a process must live longer:

```python
hw = IntelSystemConsoleSession(...)
try:
    hw.open()
    # Transfer data and query the target.
finally:
    hw.close()
```

Calls are protected by a reentrant lock, so threads cannot interleave commands
in one session. `close()` requests a clean Tcl shutdown, then terminates an
unresponsive process.

The session creates and replaces `data_in.bin` and `data_out.bin` in its work
directory. Confirm service indices and target addresses before writing: unlike
simulation, an incorrect address can modify a live board state. Startup,
timeouts, malformed responses and short reads are reported as Python errors.
