# Build the single-file Windows executable.
# Usage (from the repo root):  ./packaging/build.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Installing build dependencies..." -ForegroundColor Cyan
py -m pip install --user --upgrade pyinstaller
py -m pip install --user -e .

Write-Host "Running PyInstaller..." -ForegroundColor Cyan
py -m PyInstaller packaging/projgen.spec --clean --noconfirm

$exe = Join-Path $root "dist/ProjectionTestPatternGenerator.exe"
if (Test-Path $exe) {
    $size = "{0:N1} MB" -f ((Get-Item $exe).Length / 1MB)
    Write-Host "Built $exe ($size)" -ForegroundColor Green
} else {
    Write-Error "Build failed: executable not found."
}
