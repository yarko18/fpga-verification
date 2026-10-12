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

"""Ordered, simulator-specific fixes applied to copies of vendor models."""

import re
from pathlib import Path


def _patch1(model):
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
                raise ValueError(f"Expected one {kind} {port} declaration in {module}")
        model = model[:match.start()] + body + model[match.end():]

    return model


def _patch2(model):
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


def _patch_lpm_mult_optional_sum(model):
    """Remove four-state handling of an unconnected lpm_mult sum input."""
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


# Add independent compatibility fixes here in application order.
_MODEL_FIXES = {
    "verilator": {
        "220model.v": (("lpm_mult_optional_sum", _patch_lpm_mult_optional_sum),),
        "altera_mf.v": (("patch1", _patch1), ("patch2", _patch2)),
    },
}


def prepare_simulation_models(sources, *, simulator, output_dir, enabled=True):
    """Return model paths, copying only files with applicable fixes.

    Installed models are never modified. Unexpected model layouts fail explicitly
    rather than silently applying a partial fix. Set enabled=False to opt out.
    """
    sources = [Path(source) for source in sources]
    if not enabled:
        return sources
    fixes = _MODEL_FIXES.get(simulator, {})
    prepared = []
    for source in sources:
        steps = fixes.get(source.name, ())
        if not steps:
            prepared.append(source)
            continue
        model = source.read_text(encoding="utf-8", errors="surrogateescape")
        for name, transform in steps:
            model = transform(model)
        target = Path(output_dir).resolve() / simulator / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(model, encoding="utf-8", errors="surrogateescape")
        print(
            f"Simulation fixes ({simulator}, {', '.join(name for name, _ in steps)}): "
            f"{source} -> {target}",
            flush=True,
        )
        prepared.append(target)
    return prepared
