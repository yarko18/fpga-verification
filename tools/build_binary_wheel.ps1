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

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

foreach ($relativePath in @("build", "dist")) {
    $target = Join-Path $repoRoot $relativePath
    if (-not $target.StartsWith($repoRoot.Path, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside repository: $target"
    }
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
}

$env:FPGA_VERIFICATION_BINARY = "1"
try {
    python -m build --wheel --no-isolation
}
finally {
    Remove-Item Env:\FPGA_VERIFICATION_BINARY -ErrorAction SilentlyContinue
}

if (-not (Test-Path "dist")) {
    throw "Build finished without creating a dist directory."
}

$wheel = Get-ChildItem "dist\*.whl" | Select-Object -First 1
if ($null -eq $wheel) {
    throw "Build finished without creating a wheel."
}

Write-Host "Built $($wheel.FullName)"
python -m zipfile --list $wheel.FullName
