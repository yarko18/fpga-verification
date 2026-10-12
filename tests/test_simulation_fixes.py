# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fpga_verification.altera.quartus._simulation_fixes import (
    prepare_simulation_models,
)


RAM_MODEL = '\n'.join(
    f'''module {name}(clock0, clock1, wren_a, wren_b, rden_b);
input clock0, clock1, wren_a, wren_b, rden_b;
tri1 clock0;
tri0 wren_a;
tri0 wren_b;
tri1 rden_b;
tri1 clocken0;
endmodule'''
    for name in ('altsyncram', 'altsyncram_body')
)

FIFO_MODEL = '\n'.join(
    f'''module {name}(aclr);
input aclr;
tri0 aclr;
tri0 unused_input;
endmodule'''
    for name in ('dcfifo_async', 'dcfifo_low_latency', 'dcfifo_mixed_widths', 'dcfifo')
)

MODEL = RAM_MODEL + '\n' + FIFO_MODEL

LPM_OPTIONAL_SUM_BLOCK = '''    // if sum port is not used
    if (sum === {lpm_widths{1'bz}})
    begin
        t_s = {lpm_widths{1'b0}};
        sign_s = 1'b0;
    end'''

LPM_MODEL = f'''module unrelated;
always @* begin
{LPM_OPTIONAL_SUM_BLOCK}
end
endmodule
module lpm_mult(sum);
parameter lpm_widths = 1;
input [lpm_widths-1:0] sum;
always @* begin
{LPM_OPTIONAL_SUM_BLOCK}
end
endmodule
'''


class SimulationFixTests(unittest.TestCase):
    def test_default_copies_and_preserves_unrelated_pulls(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'altera_mf.v'
            source.write_text(MODEL)
            output = Path(directory) / 'fixed'
            log = StringIO()
            with redirect_stdout(log):
                result = prepare_simulation_models(
                    [source],
                    simulator='verilator',
                    output_dir=output,
                )
            self.assertEqual(source.read_text(), MODEL)
            fixed = result[0].read_text()
            self.assertIn(
                'Simulation fixes (verilator, altera_mf.v: '
                'altsyncram_input_pulls, dcfifo_aclr_pull)',
                log.getvalue(),
            )
            self.assertNotIn('tri1 clock0;', fixed)
            self.assertNotIn('tri0 wren_a;', fixed)
            self.assertNotIn('tri0 wren_b;', fixed)
            self.assertNotIn('tri1 rden_b;', fixed)
            self.assertEqual(fixed.count('tri1 clocken0;'), 2)
            self.assertEqual(fixed.count('input clock0, clock1, wren_a, wren_b, rden_b;'), 2)
            self.assertNotIn('tri0 aclr;', fixed)
            self.assertEqual(fixed.count('tri0 unused_input;'), 4)
            self.assertEqual(fixed.count('input aclr;'), 4)
            self.assertEqual(prepare_simulation_models([source], simulator='verilator', output_dir=output)[0].read_text(), fixed)

    def test_opt_out_and_other_simulators_do_not_touch_sources(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'altera_mf.v'
            output = Path(directory) / 'fixed'
            for simulator, enabled in [('questa', True), ('verilator', False)]:
                self.assertEqual(prepare_simulation_models([source], simulator=simulator, output_dir=output, enabled=enabled), [source])
            self.assertFalse(output.exists())

    def test_unexpected_model_fails_without_writing_copy(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'altera_mf.v'
            source.write_text(MODEL.replace('tri0 wren_a;', 'wire wren_a;', 1))
            output = Path(directory) / 'fixed'
            with self.assertRaises(ValueError):
                prepare_simulation_models([source], simulator='verilator', output_dir=output)
            self.assertFalse(output.exists())

    def test_unexpected_fifo_model_fails_without_writing_copy(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'altera_mf.v'
            source.write_text(MODEL.replace('tri0 aclr;', 'wire aclr;', 1))
            output = Path(directory) / 'fixed'
            with self.assertRaises(ValueError):
                prepare_simulation_models([source], simulator='verilator', output_dir=output)
            self.assertFalse(output.exists())

    def test_patches_lpm_mult_unconnected_sum_for_verilator(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / '220model.v'
            source.write_text(LPM_MODEL)
            output = Path(directory) / 'fixed'
            log = StringIO()
            with redirect_stdout(log):
                result = prepare_simulation_models(
                    [source],
                    simulator='verilator',
                    output_dir=output,
                )
            self.assertEqual(source.read_text(), LPM_MODEL)
            fixed = result[0].read_text()
            self.assertIn(
                'Simulation fixes (verilator, 220model.v: '
                'lpm_mult_unconnected_sum)',
                log.getvalue(),
            )
            self.assertEqual(fixed.count("sum === {lpm_widths{1'bz}}"), 1)
            self.assertIn(
                "In two-state simulation, an unconnected sum input is already zero.",
                fixed,
            )

    def test_unexpected_lpm_model_fails_without_writing_copy(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / '220model.v'
            source.write_text(LPM_MODEL.replace("sum ===", "sum ==", 2))
            output = Path(directory) / 'fixed'
            with self.assertRaises(ValueError):
                prepare_simulation_models(
                    [source],
                    simulator='verilator',
                    output_dir=output,
                )
            self.assertFalse(output.exists())

    def test_unmatched_models_pass_through(self):
        self.assertEqual(prepare_simulation_models(['unmatched.v'], simulator='verilator', output_dir='unused'), [Path('unmatched.v')])
