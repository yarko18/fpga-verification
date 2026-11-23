# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import fpga_verification
from fpga_verification.sim import ComponentConfig, hdl_parameter
from fpga_verification.sim.runners import _common, component, rtl
from fpga_verification.altera.quartus.component import (
    prepare_component_simulation,
)


class SimulationRunnerDefaultTests(unittest.TestCase):
    @dataclass
    class _Config(ComponentConfig):
        width: int = hdl_parameter(64, name="WIDTH")
        name: str = "smoke"

    def test_run_wrapper_prints_project_banner(self):
        output = StringIO()

        with (
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
            f"fpga-verification {fpga_verification.__version__} | by Yaroslav Mariukha\n",
        )

    def test_matrix_only_options_require_matrix_mode(self):
        with self.assertRaisesRegex(ValueError, "--plan requires --matrix"):
            _common._parse_run_args(["--plan"])
        with self.assertRaisesRegex(ValueError, "--jobs requires --matrix"):
            _common._parse_run_args(["--jobs", "2"])

    def test_parameter_preset_cannot_be_combined_with_matrix(self):
        with self.assertRaisesRegex(
            ValueError,
            "--param-preset cannot be combined with --matrix",
        ):
            _common._parse_run_args(
                ["--matrix", "--param-preset", "wide"],
            )

    def test_parameter_presets_are_lazy_and_default_is_implicit(self):
        constructed = []
        presets = {
            "default": lambda: constructed.append("default") or self._Config(),
            "wide": lambda: constructed.append("wide") or self._Config(width=80),
        }

        resolved = _common.resolve_parameter_config(None, presets, None)

        self.assertEqual(resolved, self._Config())
        self.assertEqual(constructed, ["default"])

    def test_explicit_parameter_preset_is_reported(self):
        output = StringIO()

        with redirect_stdout(output):
            resolved = _common.resolve_parameter_config(
                None,
                {
                    "default": self._Config(),
                    "wide": self._Config(width=80, name="selected"),
                },
                "wide",
            )

        self.assertEqual(resolved, self._Config(width=80, name="selected"))
        self.assertIn("Selected parameter preset: wide", output.getvalue())
        self.assertIn("WIDTH", output.getvalue())
        self.assertIn('"selected"', output.getvalue())

    def test_parameter_preset_validation(self):
        with self.assertRaisesRegex(
            ValueError,
            "--param-preset requires parameter_presets",
        ):
            _common.resolve_parameter_config(None, None, "wide")
        with self.assertRaisesRegex(
            ValueError,
            "config and parameter_presets cannot be used together",
        ):
            _common.resolve_parameter_config(
                self._Config(),
                {"default": self._Config()},
                None,
            )
        with self.assertRaisesRegex(
            ValueError,
            "must define a 'default' preset",
        ):
            _common.resolve_parameter_config(
                None,
                {"wide": self._Config(width=80)},
                None,
            )
        with self.assertRaisesRegex(
            ValueError,
            "Unknown parameter preset 'missing'; available: default, wide",
        ):
            _common.resolve_parameter_config(
                None,
                {
                    "default": self._Config(),
                    "wide": self._Config(width=80),
                },
                "missing",
            )

    def test_rtl_runner_resolves_selected_parameter_preset(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(rtl, "_rtl_test_cocotb") as rtl_runner,
        ):
            rtl.run_rtl_test(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                parameter_presets={
                    "default": self._Config(),
                    "wide": self._Config(width=80, name="selected"),
                },
                sources=(),
                python_paths=(),
                argv=["--param-preset", "wide"],
            )

        self.assertEqual(
            rtl_runner.call_args.kwargs["parameters"],
            {"WIDTH": 80},
        )
        self.assertEqual(
            rtl_runner.call_args.kwargs["extra_env"],
            {
                "FPGA_VERIFICATION_TEST_CONFIG_JSON": (
                    '{"name": "selected", "width": 80}'
                ),
            },
        )

    def test_test_patterns_are_available_in_ordinary_and_matrix_runs(self):
        ordinary = _common._parse_run_args(
            ["--test", "ControlPacketTest", "--test", "Video*"],
        )
        matrix = _common._parse_run_args(["--matrix", "--test", "Video*"])

        self.assertEqual(
            ordinary.test_patterns,
            ("ControlPacketTest", "Video*"),
        )
        self.assertEqual(matrix.test_patterns, ("Video*",))

    def test_test_patterns_match_full_names_or_test_class_names(self):
        expression = _common._test_filter_from_patterns(
            ("vip.test_pyuvm.ControlPacketTest", "Video*"),
        )

        import re

        self.assertIsNotNone(
            re.search(expression, "vip.test_pyuvm.ControlPacketTest"),
        )
        self.assertIsNotNone(
            re.search(expression, "vip.test_pyuvm.VideoPacketTest"),
        )
        self.assertIsNone(re.search(expression, "vip.test_pyuvm.UserPacketTest"))

    def test_coverage_can_be_combined_with_matrix_mode(self):
        args = _common._parse_run_args(["--matrix", "--coverage"])

        self.assertTrue(args.matrix)
        self.assertTrue(args.coverage)

    def test_coverage_flag_is_parsed_for_an_ordinary_run(self):
        args = _common._parse_run_args(["--coverage"])

        self.assertTrue(args.coverage)
        self.assertFalse(args.matrix)

    def test_matrix_jobs_support_number_short_option_and_max(self):
        self.assertEqual(
            _common._parse_run_args(["--matrix", "-j", "4"]).jobs,
            4,
        )
        with patch.object(_common, "_available_cpu_count", return_value=64):
            self.assertEqual(
                _common._parse_run_args(["--matrix", "--jobs", "max"]).jobs,
                64,
            )
        self.assertEqual(_common._parse_run_args(["--matrix"]).jobs, 1)

    def test_rtl_runner_defaults_to_verilator(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("cocotb_tools.runner.get_runner", return_value=runner) as get_runner,
            patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
        ):
            rtl._rtl_test_cocotb(
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
        self.assertEqual(runner.test.call_args.kwargs["extra_env"], {})

    def test_rtl_runner_debug_enables_verilator_waves(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("cocotb_tools.runner.get_runner", return_value=runner),
            patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
        ):
            rtl._rtl_test_cocotb(
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
            rtl._rtl_test_cocotb(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=[],
                extra_env={"TEST_VALUE": "value"},
            )

        self.assertEqual(runner.test.call_args.kwargs["extra_env"], {"TEST_VALUE": "value"})

    def test_rtl_runner_passes_test_filter(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with (
            patch("cocotb_tools.runner.get_runner", return_value=runner),
            patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
        ):
            rtl._rtl_test_cocotb(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=[],
                test_filter="VideoPacketTest",
            )

        self.assertEqual(
            runner.test.call_args.kwargs["test_filter"],
            "VideoPacketTest",
        )

    def test_rtl_runner_encodes_boolean_parameters_as_verilog_bits(self):
        runner = Mock()
        runner.test.return_value = Path("results.xml")

        with (
            patch("cocotb_tools.runner.get_runner", return_value=runner),
            patch("cocotb_tools.runner.get_results", return_value=(1, 0)),
        ):
            rtl._rtl_test_cocotb(
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
                "_component_test_cocotb",
            ) as component_runner,
        ):
            component.run_component_test(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=(),
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

    def test_altera_component_adds_verilator_parameter_warning_default(self):
        self.assertEqual(
            component._component_build_args("verilator", None),
            ["-Wno-PARAMNODEFAULT"],
        )
        self.assertEqual(
            component._component_build_args("verilator", ["--timing"]),
            ["-Wno-PARAMNODEFAULT", "--timing"],
        )

    def test_altera_component_does_not_duplicate_or_apply_default_to_questa(self):
        self.assertEqual(
            component._component_build_args(
                "verilator",
                ["-Wno-PARAMNODEFAULT", "--timing"],
            ),
            ["-Wno-PARAMNODEFAULT", "--timing"],
        )
        self.assertEqual(
            component._component_build_args("questa", ["+define+SIMULATION"]),
            ["+define+SIMULATION"],
        )

    def test_component_runner_delegates_quartus_preparation_to_rtl_backend(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                component,
                "prepare_component_simulation",
            ) as prepare_component,
        ):
            component._component_test_cocotb(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
            )

        self.assertIs(
            prepare_component.call_args.kwargs["rtl_backend"],
            component._rtl_test_cocotb,
        )
        self.assertEqual(
            prepare_component.call_args.kwargs["build_args"],
            ["-Wno-PARAMNODEFAULT"],
        )
        self.assertEqual(
            prepare_component.call_args.kwargs["simulator"],
            "verilator",
        )

    def test_component_preparation_passes_test_filter_to_rtl_backend(self):
        rtl_backend = Mock()

        def create_spd(command, **_kwargs):
            report_option = next(
                item for item in command if item.startswith("--report-file=spd:")
            )
            Path(report_option.removeprefix("--report-file=spd:")).touch()

        with (
            TemporaryDirectory() as temporary_dir,
            patch(
                "fpga_verification.altera.quartus.component.shutil.which",
                return_value="ip-generate",
            ),
            patch(
                "fpga_verification.altera.quartus.component._run_command",
                side_effect=create_spd,
            ),
            patch(
                "fpga_verification.altera.quartus.component._spd_hdl_sources",
                return_value=[],
            ),
            patch(
                "fpga_verification.altera.quartus.component._quartus_sim_sources",
                return_value=[],
            ),
        ):
            prepare_component_simulation(
                project_root=temporary_dir,
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                rtl_backend=rtl_backend,
                simulator="verilator",
                make_ipx=False,
                test_filter="VideoPacketTest",
            )

        self.assertEqual(
            rtl_backend.call_args.kwargs["test_filter"],
            "VideoPacketTest",
        )

    def test_altera_component_runner_serializes_resolved_config(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(component, "_component_test_cocotb") as component_runner,
        ):
            component.run_component_test(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                config=self._Config(width=80, name="matrix"),
                sources=(),
                python_paths=(),
                argv=(),
            )

        self.assertEqual(component_runner.call_args.kwargs["component_parameters"], {"WIDTH": 80})
        self.assertEqual(
            component_runner.call_args.kwargs["extra_env"],
            {"FPGA_VERIFICATION_TEST_CONFIG_JSON": '{"name": "matrix", "width": 80}'},
        )

    def test_component_runner_filters_an_ordinary_run(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(component, "_component_test_cocotb") as component_runner,
        ):
            component.run_component_test(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=(),
                python_paths=(),
                argv=["--test", "Video*"],
            )

        test_filter = component_runner.call_args.kwargs["test_filter"]
        import re

        self.assertIsNotNone(re.search(test_filter, "test_dut.VideoPacketTest"))
        self.assertIsNone(re.search(test_filter, "test_dut.UserPacketTest"))

    def test_altera_component_runner_merges_derived_parameters_after_config(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(component, "_component_test_cocotb") as component_runner,
        ):
            component.run_component_test(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                config=self._Config(width=80),
                derived_parameters=lambda cfg: {"DOUBLE_WIDTH": cfg.width * 2},
                sources=(),
                python_paths=(),
                argv=(),
            )

        self.assertEqual(
            component_runner.call_args.kwargs["component_parameters"],
            {"WIDTH": 80, "DOUBLE_WIDTH": 160},
        )

    def test_altera_component_matrix_plan_dispatches_without_running_component(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(component, "_component_test_cocotb") as component_runner,
            patch.object(component, "run_matrix") as run_matrix,
        ):
            component.run_component_test(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                config=self._Config(),
                sources=(),
                python_paths=(),
                argv=["--matrix", "--plan", "--test", "Video*"],
            )

        component_runner.assert_not_called()
        run_matrix.assert_called_once_with(
            project_root=Path("."),
            baseline=self._Config(),
            test_module="test_dut",
            test_patterns=("Video*",),
            plan_only=True,
            jobs=1,
            functional_coverage=False,
        )

    def test_rtl_matrix_plan_dispatches_without_running_simulator(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(rtl, "_rtl_test_cocotb") as rtl_runner,
            patch.object(rtl, "run_matrix") as run_matrix,
        ):
            rtl.run_rtl_test(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                config=self._Config(),
                sources=(),
                python_paths=(),
                argv=["--matrix", "--plan", "--test", "Video*"],
            )

        rtl_runner.assert_not_called()
        run_matrix.assert_called_once_with(
            project_root=Path("."),
            baseline=self._Config(),
            test_module="test_dut",
            test_patterns=("Video*",),
            plan_only=True,
            jobs=1,
            functional_coverage=False,
        )

    def test_altera_component_runner_rejects_parameters_different_from_config(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(component, "_component_test_cocotb"),
            self.assertRaisesRegex(ValueError, "must match"),
        ):
            component.run_component_test(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                config=self._Config(width=80),
                component_parameters={"WIDTH": 64},
                sources=(),
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
                "_component_test_cocotb",
            ) as component_runner,
        ):
            component.run_component_test(
                project_root=".",
                component_file="component.tcl",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=(),
                python_paths=(),
                argv=["-g"],
            )

        self.assertTrue(component_runner.call_args.kwargs["debug"])

    def test_rtl_wrapper_g_flag_enables_debug(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(rtl, "_rtl_test_cocotb") as rtl_runner,
        ):
            rtl.run_rtl_test(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=(),
                python_paths=(),
                argv=["-g"],
            )

        self.assertTrue(rtl_runner.call_args.kwargs["debug"])

    def test_rtl_wrapper_enables_functional_coverage_environment(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(
                rtl,
                "functional_coverage_environment",
                return_value={"FPGA_VERIFICATION_FUNCTIONAL_COVERAGE": "1"},
            ) as coverage_environment,
            patch.object(rtl, "_rtl_test_cocotb") as rtl_runner,
        ):
            rtl.run_rtl_test(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=(),
                python_paths=(),
                argv=["--coverage"],
            )

        coverage_environment.assert_called_once_with(
            True,
            None,
            artifacts_root=Path("."),
            defer=False,
        )
        self.assertEqual(
            rtl_runner.call_args.kwargs["extra_env"],
            {"FPGA_VERIFICATION_FUNCTIONAL_COVERAGE": "1"},
        )

    def test_rtl_wrapper_ignores_pytest_arguments(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(rtl, "_rtl_test_cocotb") as rtl_runner,
        ):
            rtl.run_rtl_test(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                sources=(),
                python_paths=(),
                argv=["-q", "tests/test_dut.py"],
            )

        self.assertFalse(rtl_runner.call_args.kwargs["debug"])

    def test_rtl_wrapper_resolves_config_for_build_and_test(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(_common, "_prepend_python_paths"),
            patch.object(_common, "_clean_sim_build"),
            patch.object(rtl, "_rtl_test_cocotb") as rtl_runner,
        ):
            rtl.run_rtl_test(
                project_root=".",
                hdl_toplevel="dut",
                test_module="test_dut",
                config=self._Config(width=80, name="matrix"),
                sources=(),
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

    def test_rtl_runner_recursively_combines_relative_and_absolute_sources(self):
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
                rtl._rtl_test_cocotb(
                    project_root=project_root,
                    hdl_toplevel="dut",
                    test_module="test_dut",
                    sources=("rtl", absolute_dir, relative_dir / "nested"),
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
                rtl._rtl_test_cocotb(
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
                rtl._rtl_test_cocotb(
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
                rtl._rtl_test_cocotb(
                    project_root=project_root,
                    hdl_toplevel="dut",
                    test_module="test_dut",
                    sources=("rtl",),
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
            rtl._rtl_test_cocotb(
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

if __name__ == "__main__":
    unittest.main()
