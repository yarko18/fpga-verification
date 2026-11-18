# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

from importlib.metadata import version

import fpga_verification


def test_package_exposes_installed_distribution_version():
    assert fpga_verification.__version__ == version("fpga-verification")
