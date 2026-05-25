<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: Apache-2.0
-->

# fpga-verification

Reusable FPGA verification helpers. The package currently provides data formats
and cocotb simulation utilities; HIL support can be added under a separate
`hil` namespace without coupling it to simulation.

## Package Layout

```text
src/fpga_verification/
  formats/
    integer.py             # UIntFormat
  sim/
    platform_designer.py  # Platform Designer generated-system simulation
    buses/
      avalon_st.py         # Avalon-ST cocotb source/sink/monitor
    intel_video/
      vip.py               # Intel Video packet models
    runners/
      rtl.py               # Generic cocotb RTL runner
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

After reinstalling a previous development version:

```powershell
python -m pip uninstall fpga-cocotb -y
python -m pip install -e ".[sim]"
```

## Imports

```python
from fpga_verification.formats import UIntFormat
from fpga_verification.sim.buses import AvalonSTSink, AvalonSTSource
from fpga_verification.sim.intel_video import VIPControlPacket
from fpga_verification.sim.platform_designer import platform_test_cocotb
from fpga_verification.sim.runners import rtl_test_cocotb
```
