# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0

"""Reusable, IP-independent behavioural-model utilities.

IP behaviour belongs beside its custom scoreboard.  This package deliberately
does not provide a generic VIP predictor: a protocol scoreboard cannot know an
IP's register and temporal semantics.
"""
