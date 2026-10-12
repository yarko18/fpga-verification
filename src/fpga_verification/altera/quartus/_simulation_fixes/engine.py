# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

"""Apply ordered simulator fixes without modifying installed vendor models."""

from pathlib import Path

from .registry import MODEL_FIXES


def prepare_simulation_models(sources, *, simulator, output_dir, enabled=True):
    """Return model paths, copying only files with applicable fixes.

    Installed models are never modified. Unexpected model layouts fail explicitly
    rather than silently applying a partial fix. Set enabled=False to opt out.
    """
    sources = [Path(source) for source in sources]
    if not enabled:
        return sources

    fixes = MODEL_FIXES.get(simulator, {})
    prepared = []
    for source in sources:
        steps = fixes.get(source.name, ())
        if not steps:
            prepared.append(source)
            continue

        model = source.read_text(encoding="utf-8", errors="surrogateescape")
        for step in steps:
            model = step.transform(model)

        target = Path(output_dir).resolve() / simulator / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(model, encoding="utf-8", errors="surrogateescape")
        names = ", ".join(step.name for step in steps)
        print(
            f"Simulation fixes ({simulator}, {source.name}: {names}): "
            f"{source} -> {target}",
            flush=True,
        )
        prepared.append(target)

    return prepared
