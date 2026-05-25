<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: Apache-2.0
-->

# fpga-verification

Reusable FPGA verification helpers. The package provides shared data formats,
cocotb simulation utilities, and an Intel System Console HIL transport.

## Package Layout

```text
src/fpga_verification/
  formats/
    integer.py             # UIntFormat
    fixed_point.py         # QFormat
  sim/
    platform_designer.py  # Platform Designer generated-system simulation
    buses/
      avalon_st.py         # Avalon-ST cocotb source/sink/monitor
    intel_video/
      vip.py               # Intel Video packet models
    runners/
      rtl.py               # Generic cocotb RTL runner
  hil/
    intel/
      system_console.py    # Persistent Avalon-MM and JTAG UART session
      resources/
        jtag_session.tcl   # System Console worker
```

## Install

For format-only use:

```powershell
python -m pip install -e .
```

For simulation use:

```powershell
python -m pip install -e ".[sim]"
```

For hardware-in-the-loop use:

```powershell
python -m pip install -e ".[hil]"
```

For both:

```powershell
python -m pip install -e ".[all]"
```

After reinstalling a previous development version:

```powershell
python -m pip uninstall fpga-cocotb -y
python -m pip install -e ".[all]"
```

## Imports

```python
from fpga_verification.formats import QFormat, UIntFormat
from fpga_verification.sim.buses import AvalonSTSink, AvalonSTSource
from fpga_verification.sim.intel_video import VIPControlPacket
from fpga_verification.sim.platform_designer import platform_test_cocotb
from fpga_verification.sim.runners import rtl_test_cocotb
from fpga_verification.hil.intel import IntelSystemConsoleSession
```

`UIntFormat` models unscaled unsigned fields such as bus symbols or pixels.
`QFormat` models fixed-point raw storage and arithmetic; for signed formats,
the integer width includes the sign bit.

## HIL Session

`IntelSystemConsoleSession` opens one persistent `system-console` process and
uses it sequentially for Avalon-MM memory access and JTAG UART commands.

```python
from fpga_verification.hil.intel import IntelSystemConsoleSession

with IntelSystemConsoleSession() as hw:
    hw.write_memory(frame, 0x01E84800)
    print(hw.command("g\n"))
    frame_out = hw.read_memory((1024, 1280), 0x02DC6C00)
```

Intel Quartus `system-console` must be available on `PATH`.
