# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Ordered registry of simulator-specific vendor model fixes."""

from .patches.verilator.altera_mf_altsyncram_input_pulls import (
    PATCH as ALTERA_MF_ALTSYNCRAM_INPUT_PULLS,
)
from .patches.verilator.altera_mf_dcfifo_aclr_pull import (
    PATCH as ALTERA_MF_DCFIFO_ACLR_PULL,
)
from .patches.verilator.lpm_mult_unconnected_sum import (
    PATCH as LPM_MULT_UNCONNECTED_SUM,
)


MODEL_FIXES = {
    "verilator": {
        "220model.v": (LPM_MULT_UNCONNECTED_SUM,),
        "altera_mf.v": (
            ALTERA_MF_ALTSYNCRAM_INPUT_PULLS,
            ALTERA_MF_DCFIFO_ACLR_PULL,
        ),
    },
}
