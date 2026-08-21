param(
    [switch]$SkipHermesCheck
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $repository

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe" -PathType Leaf)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw "Python 3.11 or newer is required."
    }
}

& ".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3, 11), sys.version"
& ".venv\Scripts\python.exe" -m pip install "uv==0.12.5"
& ".venv\Scripts\uv.exe" sync --all-extras --frozen
& ".venv\Scripts\opportunityos.exe" setup
& ".venv\Scripts\opportunityos.exe" doctor

if (-not $SkipHermesCheck) {
    if (Get-Command hermes -ErrorAction SilentlyContinue) {
        & hermes --version
        Write-Host "Hermes detected. Continue with docs/HERMES_SETUP.md."
    } else {
        Write-Host "Hermes is GATED. Review the current official installer, then follow docs/HERMES_SETUP.md."
    }
}
