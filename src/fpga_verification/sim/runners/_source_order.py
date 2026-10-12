# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

"""Simulator-independent Verilog and SystemVerilog source ordering."""

import heapq
from pathlib import Path


def order_sources(sources, *, include_dirs=(), defines=None):
    """Return *sources* in dependency-safe compilation order."""
    from vunit.dependency_graph import CircularDependencyException
    from vunit.project import Project

    project = Project()
    project.add_library("rtl", ".")

    for source in sources:
        source = Path(source)
        project.add_source_file(
            source,
            "rtl",
            file_type=(
                "systemverilog" if source.suffix.lower() == ".sv" else "verilog"
            ),
            include_dirs=[str(path) for path in include_dirs],
            defines=dict(defines or {}),
        )

    source_files = project.get_source_files_in_order()
    dependency_graph = project.create_dependency_graph()
    position = {source: index for index, source in enumerate(source_files)}
    dependencies = {
        source: set(dependency_graph.get_direct_dependencies(source))
        for source in source_files
    }
    dependents = {source: [] for source in source_files}
    for source, required in dependencies.items():
        for dependency in required:
            dependents[dependency].append(source)

    ready = [
        position[source]
        for source in source_files
        if not dependencies[source]
    ]
    heapq.heapify(ready)
    ordered = []

    while ready:
        source = source_files[heapq.heappop(ready)]
        ordered.append(source)
        for dependent in dependents[source]:
            dependencies[dependent].remove(source)
            if not dependencies[dependent]:
                heapq.heappush(ready, position[dependent])

    if len(ordered) != len(source_files):
        try:
            dependency_graph.toposort()
        except CircularDependencyException as error:
            cycle = " -> ".join(str(source.name) for source in error.path)
            raise ValueError(f"Circular RTL source dependency: {cycle}") from error
        raise ValueError("Unable to determine RTL source order")

    return [Path(source.name) for source in ordered]
