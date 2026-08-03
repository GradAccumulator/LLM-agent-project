$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path `
    $ProjectRoot `
    ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    & $VenvPython -m src.main --edge-cdp-start
}
else {
    python -m src.main --edge-cdp-start
}

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
