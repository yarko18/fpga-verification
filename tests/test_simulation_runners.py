# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from fpga_verification.sim import platform_designer
from fpga_verification.sim.runners import _common, intel_component, rtl


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

    def test_rtl_runner_debug_enables_verilator_waves(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("cocotb_tools.runner.get_runner", return_value=runner),
            patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
        ):
            rtl.rtl_test_cocotb(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=[],
                debug=True,
            )

        self.assertTrue(runner.build.call_args.kwargs["waves"])
        self.assertTrue(runner.test.call_args.kwargs["waves"])
        self.assertFalse(runner.test.call_args.kwargs["gui"])

    def test_intel_component_wrapper_defaults_to_verilator(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build") as clean_sim_build,
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
                argv=(),
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

    def test_intel_component_wrapper_g_flag_enables_debug(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
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
                argv=["-g"],
            )

        self.assertTrue(component_runner.call_args.kwargs["debug"])

    def test_rtl_wrapper_g_flag_enables_debug(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(rtl, "rtl_test_cocotb") as rtl_runner,
        ):
            rtl.run_rtl_test(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                source_dirs=(),
                python_paths=(),
                argv=["-g"],
            )

        self.assertTrue(rtl_runner.call_args.kwargs["debug"])

    def test_rtl_wrapper_ignores_pytest_arguments(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(rtl, "rtl_test_cocotb") as rtl_runner,
        ):
            rtl.run_rtl_test(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                source_dirs=(),
                python_paths=(),
                argv=["-q", "tests/test_dut.py"],
            )

        self.assertFalse(rtl_runner.call_args.kwargs["debug"])

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
