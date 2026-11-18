# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Installed distribution version exposed by :mod:`fpga_verification`."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("fpga-verification")
except PackageNotFoundError:
    # Keep imports useful from an unpacked source tree that has not been
    # installed yet. Released wheels and editable installs always use metadata.
    __version__ = "development"
