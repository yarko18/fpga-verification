# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Remove connected input pulls from nested ``altsyncram`` models."""

import re

from ...model import ModelFix


def apply(model):
    """Work around nested altsyncram input pulls in Verilator."""
    for module in ("altsyncram", "altsyncram_body"):
        pattern = rf"(?ms)^module\s+{module}\s*\(.*?^endmodule\b"
        matches = list(re.finditer(pattern, model))
        if len(matches) != 1:
            raise ValueError(f"Expected one {module} module in altera_mf.v")
        match = matches[0]
        body = match.group()
        for kind, port in (
            ("tri0", "wren_a"),
            ("tri0", "wren_b"),
            ("tri1", "rden_b"),
            ("tri1", "clock0"),
        ):
            body, count = re.subn(
                rf"(?m)^[ \t]*{kind}[ \t]+{port}[ \t]*;[ \t]*$",
                f"    // RAM model workaround: use the connected input {port}.",
                body,
            )
            if count != 1:
                raise ValueError(
                    f"Expected one {kind} {port} declaration in {module}"
                )
        model = model[:match.start()] + body + model[match.end():]

    return model


PATCH = ModelFix(name="altsyncram_input_pulls", transform=apply)
