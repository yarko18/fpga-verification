# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fpga_verification.sim import platform_designer
from fpga_verification.sim.runners import intel_component, rtl


class SimulationRunnerDefaultTests(unittest.TestCase):
    def test_rtl_runner_defaults_to_verilator(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("cocotb_tools.runner.get_runner", return_value=runner) as get_runner,
            patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
        ):
            rtl.rtl_test_cocotb(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=[],
                build_args=["-Wno-PARAMNODEFAULT"],
            )

        get_runner.assert_called_once_with("verilator")
        self.assertEqual(
            runner.build.call_args.kwargs["build_dir"],
            Path("sim_build_verilator"),
        )
        self.assertIn(
            "-Wno-PARAMNODEFAULT",
            runner.build.call_args.kwargs["build_args"],
        )

    def test_intel_component_wrapper_defaults_to_verilator(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                intel_component,
                "_parse_run_args",
                return_value=SimpleNamespace(debug=False),
            ),
            patch.object(intel_component, "_prepend_python_paths"),
            patch.object(intel_component, "_clean_sim_build") as clean_sim_build,
            patch.object(
                intel_component,
                "intel_component_test_cocotb",
            ) as component_runner,
        ):
            intel_component.run_intel_component_test(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                source_dirs=(),
                python_paths=(),
                build_args=["-Wno-PARAMNODEFAULT"],
                test_args=["--trace-depth", "8"],
            )

        clean_sim_build.assert_called_once_with(Path("."), "verilator")
        self.assertEqual(
            component_runner.call_args.kwargs["compile_log"],
            Path("logs/verilator_compile.log"),
        )
        self.assertEqual(
            component_runner.call_args.kwargs["build_args"],
            ["-Wno-PARAMNODEFAULT"],
        )
        self.assertEqual(
            component_runner.call_args.kwargs["test_args"],
            ["--trace-depth", "8"],
        )

    def test_rtl_runner_appends_questa_build_and_test_args(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with (
            patch.dict(os.environ, {"SIM": "questa"}, clear=True),
            patch("cocotb_tools.runner.get_runner", return_value=runner),
            patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
        ):
            rtl.rtl_test_cocotb(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=[],
                build_args=["+define+SIMULATION"],
                test_args=["-suppress", "12110"],
            )

        self.assertEqual(
            runner.build.call_args.kwargs["build_args"],
            ["-timescale", "1ns/1ps", "+define+SIMULATION"],
        )
        self.assertEqual(
            runner.test.call_args.kwargs["test_args"],
            ["-no_autoacc", "-suppress", "12110"],
        )

    def test_platform_runner_defaults_to_verilator(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(platform_designer, "run_verilator") as run_verilator,
            patch.object(platform_designer, "run_questa") as run_questa,
        ):
            platform_designer.platform_test_cocotb(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
            )

        run_verilator.assert_called_once_with(".", "dut", "test_dut", False)
        run_questa.assert_not_called()


if __name__ == "__main__":
    unittest.main()
