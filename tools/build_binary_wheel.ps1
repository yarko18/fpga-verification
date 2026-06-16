# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: Apache-2.0

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
