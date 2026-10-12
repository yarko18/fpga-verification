# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Remove four-state handling of an unconnected ``lpm_mult`` sum input."""

import re

from ...model import ModelFix


def apply(model):
    """Remove the unsupported optional-sum four-state check for Verilator."""
    module_pattern = r"(?ms)^module\s+lpm_mult\s*\(.*?^endmodule\b"
    matches = list(re.finditer(module_pattern, model))
    if len(matches) != 1:
        raise ValueError("Expected one lpm_mult module in 220model.v")

    match = matches[0]
    body, count = re.subn(
        r"""(?mx)
        ^[ \t]*//[ \t]*if[ \t]+sum[ \t]+port[ \t]+is[ \t]+not[ \t]+used[ \t]*\n
        ^[ \t]*if[ \t]*\([ \t]*sum[ \t]*===[ \t]*\{lpm_widths\{1'bz\}\}[ \t]*\)[ \t]*\n
        ^[ \t]*begin[ \t]*\n
        ^[ \t]*t_s[ \t]*=[ \t]*\{lpm_widths\{1'b0\}\};[ \t]*\n
        ^[ \t]*sign_s[ \t]*=[ \t]*1'b0;[ \t]*\n
        ^[ \t]*end[ \t]*$
        """,
        "        // In two-state simulation, an unconnected sum input is already zero.",
        match.group(),
    )
    if count != 1:
        raise ValueError("Expected one optional sum block in lpm_mult")

    return model[:match.start()] + body + model[match.end():]


PATCH = ModelFix(name="lpm_mult_unconnected_sum", transform=apply)
