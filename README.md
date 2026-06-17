<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: Apache-2.0
-->

# fpga-verification

Reusable FPGA verification helpers. The package provides shared data formats,
wire-protocol codecs, cocotb simulation utilities, and an Intel System Console
HIL transport.

## Package Layout

```text
src/fpga_verification/
  formats/
    integer.py             # UIntFormat
    fixed_point.py         # QFormat
  protocols/
    avalon_st/
      intel_video/
        packets.py         # Intel Avalon-ST Video packet codecs
  sim/
    platform_designer.py  # Platform Designer generated-system simulation
    buses/
      avalon_st.py         # Avalon-ST cocotb source/sink/monitor
    bfms/
      intel_dma.py         # Intel read/write DMA component BFM
    runners/
      intel_component.py   # Intel component generation over the RTL runner
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

## Closed-source binary wheel

This project can build a platform-specific binary wheel with Cython. The wheel
contains compiled extension modules (`.pyd` on Windows, `.so` on Linux/macOS)
instead of the package's `.py` source files.

See [docs/binary_wheel.md](docs/binary_wheel.md) for the full command list:
build, check, install, uninstall, cleanup, and publish.

This is source hiding, not strong code protection: compiled Python extensions
can still be inspected or reverse engineered. Do not publish a source
distribution (`sdist`) if you do not want to distribute the Python sources.

Install the build tools:

```powershell
python -m pip install --upgrade build twine Cython wheel
```

Build a local binary wheel:

```powershell
.\tools\build_binary_wheel.ps1
```

Install the produced wheel locally:

```powershell
python -m pip install .\dist\fpga_verification-0.2.0-*.whl
```

Publish only wheel files, not `*.tar.gz` source archives:

```powershell
python -m twine upload --repository testpypi dist\*.whl
python -m pip install --index-url https://test.pypi.org/simple/ fpga-verification

python -m twine upload dist\*.whl
python -m pip install fpga-verification
```

Binary wheels are specific to the Python version, operating system, CPU
architecture, and sometimes the C runtime used to build them. For public PyPI
distribution, build and upload one wheel for every platform and Python version
you want to support. `cibuildwheel` is the usual CI tool for that.

This repository includes a GitHub Actions workflow at
`.github/workflows/wheels.yml` that builds binary wheels for:

```text
cp310, cp311, cp312, cp313, cp314
Windows x64
Linux x64
macOS x64 and arm64
```

The workflow uploads wheels as GitHub Actions artifacts on pushes, pull
requests, and manual runs. When you publish a GitHub Release, it uploads only
the built wheels to PyPI through Trusted Publishing. It intentionally does not
build or upload an `sdist`.

To publish publicly:

1. Push this repository to GitHub. It may stay private; PyPI users only receive
   the wheels.
2. Create the `fpga-verification` project on PyPI, or prepare the first upload.
3. In PyPI, configure Trusted Publisher for this GitHub repository:
   workflow name `wheels.yml`, environment `pypi`.
4. Push a tag and create a GitHub Release from it.
5. After the release workflow succeeds, users can install with:

```powershell
python -m pip install fpga-verification
python -m pip install "fpga-verification[all]"
```

After reinstalling a previous development version:

```powershell
python -m pip uninstall fpga-verification -y
python -m pip install -e ".[all]"
```

## Imports

```python
from fpga_verification.formats import QFormat, UIntFormat
from fpga_verification.protocols.avalon_st.intel_video import VIPControlPacket
from fpga_verification.sim.buses import AvalonSTMonitor, AvalonSTSink, AvalonSTSource
from fpga_verification.sim.bfms.intel_dma import (
    DMAAddressRegion,
    IntelDMABFM,
    IntelDMACommandMonitor,
    SparseByteMemory,
)
from fpga_verification.sim.platform_designer import platform_test_cocotb
from fpga_verification.sim.runners import intel_component_test_cocotb, rtl_test_cocotb
from fpga_verification.hil.intel import IntelSystemConsoleSession
```

`UIntFormat` models unscaled unsigned fields such as bus symbols or pixels.
`QFormat` models fixed-point raw storage and arithmetic; for signed formats,
the integer width includes the sign bit.

## Avalon-ST Protocols

`fpga_verification.protocols.avalon_st` contains packet encoders and decoders,
independent of cocotb and simulator state. `intel_video` implements the Intel
Avalon-ST Video packet format. Additional project-specific protocols can be
placed alongside it without mixing them with bus drivers or component models.

## Intel DMA BFM

`IntelDMABFM` models paired Intel read and write DMA streaming interfaces using
Avalon-ST command, response, and payload buses. It accepts an optional shared
`SparseByteMemory` instance for initializing read data and inspecting written
data. The class is named for Intel because its descriptor bit layouts are
specific to those DMA components.

`IntelDMACommandMonitor` is a passive descriptor monitor for the Intel DMA
command streams. It can decode read/write descriptors and optionally check that
descriptor address ranges stay inside allowed `DMAAddressRegion` intervals. It
can either create its own Avalon-ST command monitors from bus handles or consume
existing `AvalonSTMonitor` objects owned by a test environment.

```python
from fpga_verification.sim.bfms.intel_dma import (
    DMAAddressRegion,
    IntelDMABFM,
    IntelDMACommandMonitor,
    SparseByteMemory,
)

memory = SparseByteMemory()
memory.write(0x1000, b"\x01\x02\x03\x04")
dma = IntelDMABFM(dut, memory=memory).start()

dma_commands = IntelDMACommandMonitor(
    clock=dut.mem_clk,
    reset=dut.mem_reset,
    rdma_cmd_bus=rdma_cmd_bus,
    wdma_cmd_bus=wdma_cmd_bus,
    read_address_regions=[DMAAddressRegion("input", 0x1000, 0x4000)],
    write_address_regions=[DMAAddressRegion("output", 0x8000, 0x4000)],
).start()
```

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

## Simulation Runners

The simulation helpers cover three levels of generated and non-generated
designs:

```text
rtl_runner
  RTL sources -> cocotb build/test

intel_component_runner
  *_hw.tcl -> ip-generate -> generated composition HDL + original RTL -> rtl_runner

platform_runner
  already generated Platform Designer sim dir/msim_setup.tcl -> simulator flow
```

`rtl_test_cocotb` is the direct RTL path. Pass it explicit HDL sources or source
directories, and it delegates build/test to the selected cocotb simulator runner.

`intel_component_test_cocotb` is for Platform Designer component `.tcl` files.
It generates only the HDL needed for simulation, keeps composition HDL that has
no source equivalent, replaces generated copies of project RTL with exact
matches from `source_dirs`, and then calls `rtl_test_cocotb`.

Its generated-catalog flow is:

```text
source_dirs
  -> ip-make-ipx --thorough-descent --source-directory=<source_dirs>
  -> components.ipx in generated temp dir
  -> ip-generate --search-path=<components.ipx>,$
  -> parse .spd
  -> replace generated RTL copies with original source files
  -> rtl_test_cocotb
```

Pass `generate_only=True` to retain and return the generated composition
directory without running simulation.

`platform_test_cocotb` is for already generated Platform Designer simulation
trees. The expected layout is:

```text
project_root/
  <hdl_toplevel>/
    <hdl_toplevel>/
      testbench/
        mentor/
          msim_setup.tcl
```

For Questa, the platform runner compiles through `msim_setup.tcl` and runs
cocotb against the generated simulator libraries. For Verilator, it reads
Verilog/SystemVerilog sources from `msim_setup.tcl` and builds them directly.
