# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fpga_verification.sim.runners._simulation_fixes import prepare_simulation_models


MODEL = '\n'.join(
    f'''module {name}(clock0, wren_a, rden_b);
input clock0, wren_a, rden_b;
tri1 clock0;
tri0 wren_a;
tri1 rden_b;
tri1 clocken0;
endmodule'''
    for name in ('altsyncram', 'altsyncram_body')
)


class SimulationFixTests(unittest.TestCase):
    def test_default_copies_and_preserves_unrelated_pulls(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'altera_mf.v'
            source.write_text(MODEL)
            output = Path(directory) / 'fixed'
            result = prepare_simulation_models([source], simulator='verilator', output_dir=output)
            self.assertEqual(source.read_text(), MODEL)
            fixed = result[0].read_text()
            self.assertNotIn('tri1 clock0;', fixed)
            self.assertNotIn('tri0 wren_a;', fixed)
            self.assertNotIn('tri1 rden_b;', fixed)
            self.assertEqual(fixed.count('tri1 clocken0;'), 2)
            self.assertEqual(fixed.count('input clock0, wren_a, rden_b;'), 2)
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

    def test_unmatched_models_pass_through(self):
        self.assertEqual(prepare_simulation_models(['220model.v'], simulator='verilator', output_dir='unused'), [Path('220model.v')])
