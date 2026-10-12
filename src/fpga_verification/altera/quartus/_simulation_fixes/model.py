# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Simulation model fix description."""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ModelFix:
    """One named text transformation for a copied vendor model."""

    name: str
    transform: Callable[[str], str]
