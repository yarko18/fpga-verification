# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_py import build_py as _build_py


ROOT = Path(__file__).parent
SRC_ROOT = ROOT / "src"
PACKAGE_ROOT = SRC_ROOT / "fpga_verification"
BINARY_BUILD = os.environ.get("FPGA_VERIFICATION_BINARY") == "1"


def _module_name(path):
    rel = path.relative_to(SRC_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _cython_extensions():
    if not BINARY_BUILD:
        return []

    from Cython.Build import cythonize

    extensions = [
        Extension(_module_name(path), [path.relative_to(ROOT).as_posix()])
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
    ]

    return cythonize(
        extensions,
        build_dir=str(ROOT / "build" / "cython"),
        compiler_directives={
            "language_level": "3",
            "embedsignature": True,
        },
        annotate=False,
    )


class BinaryBuildPy(_build_py):
    def find_package_modules(self, package, package_dir):
        if BINARY_BUILD:
            return []
        return super().find_package_modules(package, package_dir)


setup(
    ext_modules=_cython_extensions(),
    cmdclass={"build_py": BinaryBuildPy} if BINARY_BUILD else {},
)
