# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5
#
# Unless explicitly acquired and licensed from Licensor under another license,
# the contents of this file are subject to the Reciprocal Public License ("RPL")
# Version 1.5, or subsequent versions as allowed by the RPL, and You may not copy
# or use this file in either source code or executable form, except in compliance
# with the terms and conditions of the RPL.
#
# All software distributed under the RPL is provided strictly on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, AND LICENSOR
# HEREBY DISCLAIMS ALL SUCH WARRANTIES, INCLUDING WITHOUT LIMITATION, ANY
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, QUIET
# ENJOYMENT, OR NON-INFRINGEMENT. See the RPL for specific language governing
# rights and limitations under the RPL.

from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from fpga_verification.altera.quartus import component, platform_designer
from fpga_verification.altera.quartus import rtl as altera_rtl
from fpga_verification.sim import ComponentConfig, hdl_parameter
from fpga_verification.sim.runners import _common, rtl


class SimulationRunnerDefaultTests(unittest.TestCase):
    @dataclass
    class _Config(ComponentConfig):
        width: int = hdl_parameter(64, name="WIDTH")
        name: str = "smoke"

    def test_run_wrapper_prints_project_banner(self):
        output = StringIO()

        with (
            patch.object(_common, "version", return_value="1.2.3"),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            redirect_stdout(output),
        ):
            _common.prepare_test_run(
                project_root=".",
                python_paths=(),
                argv=(),
            )

        self.assertEqual(
            output.getvalue(),
            "fpga-verification 1.2.3 | Yaroslav Mariukha\n",
        )

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

    def test_rtl_runner_passes_extra_environment(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with (
            patch("cocotb_tools.runner.get_runner", return_value=runner),
            patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
        ):
            rtl.rtl_test_cocotb(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=[],
                extra_env={"TEST_VALUE": "value"},
            )

        self.assertEqual(runner.test.call_args.kwargs["extra_env"], {"TEST_VALUE": "value"})

    def test_rtl_runner_encodes_boolean_parameters_as_verilog_bits(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with (
            patch("cocotb_tools.runner.get_runner", return_value=runner),
            patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
        ):
            rtl.rtl_test_cocotb(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=[],
                parameters={"ENABLED": True, "BYPASS": False, "WIDTH": 32},
            )

        self.assertEqual(
            runner.build.call_args.kwargs["parameters"],
            {"ENABLED": 1, "BYPASS": 0, "WIDTH": 32},
        )

    def test_altera_component_wrapper_defaults_to_verilator(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build") as clean_sim_build,
            patch.object(
                component,
                "component_test_cocotb",
            ) as component_runner,
        ):
            component.run_component_test(
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

    def test_altera_component_runner_serializes_resolved_config(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(component, "component_test_cocotb") as component_runner,
        ):
            component.run_component_test(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                config=self._Config(width=80, name="matrix"),
                source_dirs=(),
                python_paths=(),
                argv=(),
            )

        self.assertEqual(component_runner.call_args.kwargs["component_parameters"], {"WIDTH": 80})
        self.assertEqual(
            component_runner.call_args.kwargs["extra_env"],
            {"FPGA_VERIFICATION_TEST_CONFIG_JSON": '{"name": "matrix", "width": 80}'},
        )
    def test_altera_component_runner_rejects_parameters_different_from_config(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(component, "component_test_cocotb"),
            self.assertRaisesRegex(ValueError, "must match"),
        ):
            component.run_component_test(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                config=self._Config(width=80),
                component_parameters={"WIDTH": 64},
                source_dirs=(),
                python_paths=(),
                argv=(),
            )

    def test_altera_component_wrapper_g_flag_enables_debug(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(
                component,
                "component_test_cocotb",
            ) as component_runner,
        ):
            component.run_component_test(
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

    def test_rtl_wrapper_resolves_config_for_build_and_test(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(altera_rtl, "rtl_test_cocotb") as rtl_runner,
        ):
            altera_rtl.run_rtl_test(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                config=self._Config(width=80, name="matrix"),
                source_dirs=(),
                intel_libraries=("altera_mf",),
                quartus_sim_lib="vendor/models",
                python_paths=(),
                argv=(),
            )

        self.assertEqual(
            rtl_runner.call_args.kwargs["parameters"],
            {"WIDTH": 80},
        )
        self.assertEqual(
            rtl_runner.call_args.kwargs["extra_env"],
            {"FPGA_VERIFICATION_TEST_CONFIG_JSON": '{"name": "matrix", "width": 80}'},
        )
        self.assertEqual(
            rtl_runner.call_args.kwargs["intel_libraries"],
            ("altera_mf",),
        )
        self.assertEqual(
            rtl_runner.call_args.kwargs["quartus_sim_lib"],
            "vendor/models",
        )

    def test_rtl_runner_recursively_combines_relative_and_absolute_source_dirs(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with TemporaryDirectory() as directory:
            project_root = Path(directory) / "project"
            relative_dir = project_root / "rtl"
            absolute_dir = Path(directory) / "shared"
            (relative_dir / "nested").mkdir(parents=True)
            absolute_dir.mkdir()
            first = relative_dir / "dut.v"
            second = relative_dir / "nested" / "helper.sv"
            third = absolute_dir / "shared.V"
            ignored = absolute_dir / "notes.txt"
            for source in (first, second, third, ignored):
                source.write_text("")

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("cocotb_tools.runner.get_runner", return_value=runner),
                patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
            ):
                rtl.rtl_test_cocotb(
                    project_root=project_root,
                    hdl_toplevel="dut",
                    test_module="test_dut",
                    source_dirs=("rtl", absolute_dir, relative_dir / "nested"),
                )

        self.assertEqual(
            runner.build.call_args.kwargs["sources"],
            [first, second, third],
        )

    def test_rtl_runner_accepts_mixed_directories_and_files_and_orders_packages(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with TemporaryDirectory() as directory:
            project_root = Path(directory) / "project"
            rtl_dir = project_root / "rtl"
            package = rtl_dir / "z_types_pkg.sv"
            consumer = rtl_dir / "a_consumer.sv"
            standalone = project_root / "standalone.v"
            rtl_dir.mkdir(parents=True)
            package.write_text("package types_pkg; typedef logic data_t; endpackage")
            consumer.write_text(
                "module consumer; import types_pkg::*; data_t data; endmodule"
            )
            standalone.write_text("module standalone; endmodule")

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("cocotb_tools.runner.get_runner", return_value=runner),
                patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
            ):
                rtl.rtl_test_cocotb(
                    project_root=project_root,
                    hdl_toplevel="consumer",
                    test_module="test_dut",
                    sources=("rtl", "standalone.v"),
                )

        self.assertEqual(
            runner.build.call_args.kwargs["sources"],
            [package, consumer, standalone],
        )

    def test_rtl_runner_preserves_explicit_file_order(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with TemporaryDirectory() as directory:
            project_root = Path(directory)
            first = project_root / "first.sv"
            second = project_root / "second.sv"
            first.write_text("")
            second.write_text("")

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("cocotb_tools.runner.get_runner", return_value=runner),
                patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
            ):
                rtl.rtl_test_cocotb(
                    project_root=project_root,
                    hdl_toplevel="dut",
                    test_module="test_dut",
                    sources=("second.sv", "first.sv"),
                )

        self.assertEqual(
            runner.build.call_args.kwargs["sources"],
            [second, first],
        )

    def test_rtl_runner_compiles_intel_models_before_user_sources(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with TemporaryDirectory() as directory:
            project_root = Path(directory) / "project"
            sim_lib = Path(directory) / "quartus" / "eda" / "sim_lib"
            source_dir = project_root / "rtl"
            sim_lib.mkdir(parents=True)
            source_dir.mkdir(parents=True)
            lpm = sim_lib / "220model.v"
            altera_mf = sim_lib / "altera_mf.v"
            dut = source_dir / "dut.sv"
            for source in (lpm, altera_mf, dut):
                source.write_text("")

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("cocotb_tools.runner.get_runner", return_value=runner),
                patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
            ):
                altera_rtl.rtl_test_cocotb(
                    project_root=project_root,
                    hdl_toplevel="dut",
                    test_module="test_dut",
                    source_dirs=("rtl",),
                    intel_libraries=("lpm", "altera_mf"),
                    quartus_sim_lib=sim_lib,
                    apply_simulation_fixes=False,
                )

        self.assertEqual(
            runner.build.call_args.kwargs["sources"],
            [lpm.resolve(), altera_mf.resolve(), dut],
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
