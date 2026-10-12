# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

"""Remove connected clear pulls from nested ``dcfifo`` models."""

import re

from ...model import ModelFix


def apply(model):
    """Work around nested dcfifo clear input pulls in Verilator."""
    for module in (
        "dcfifo_async",
        "dcfifo_low_latency",
        "dcfifo_mixed_widths",
        "dcfifo",
    ):
        pattern = rf"(?ms)^module\s+{module}\s*\(.*?^endmodule\b"
        matches = list(re.finditer(pattern, model))
        if len(matches) != 1:
            raise ValueError(f"Expected one {module} module in altera_mf.v")
        match = matches[0]
        body, count = re.subn(
            r"(?m)^[ \t]*tri0[ \t]+aclr[ \t]*;[ \t]*$",
            "    // FIFO model workaround: use the connected aclr input.",
            match.group(),
        )
        if count != 1:
            raise ValueError(f"Expected one tri0 aclr declaration in {module}")
        model = model[:match.start()] + body + model[match.end():]

    return model


PATCH = ModelFix(name="dcfifo_aclr_pull", transform=apply)
