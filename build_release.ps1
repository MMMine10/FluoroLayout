$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root '.venv-build'

if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python 3 was not found. Install Python 3.10 or later and try again.'
}

$launcher = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }

if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
    & $launcher -m venv $venv
}

$python = Join-Path $venv 'Scripts\python.exe'
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $root 'requirements.txt') pyinstaller

Push-Location $root
try {
    & $python -m PyInstaller --noconfirm --clean FluoroLayout.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

Write-Host "Build complete: $(Join-Path $root 'dist\FluoroLayout.exe')"
