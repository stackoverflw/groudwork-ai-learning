# Bootstrap a local Python environment; runtime never downloads dependencies.
param([string]$Python)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (!(Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if ($Python) {
        & $Python -m venv .venv
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw 'Install Python 3.11 or pass -Python with the interpreter path.'
    }
    if ($LASTEXITCODE) { throw 'venv creation failed' }
}
$localPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $localPython -c "import sys; sys.exit(sys.version_info[:2] != (3, 11))"
if ($LASTEXITCODE) { throw 'Groundwork needs Python 3.11. Use a Python 3.11 interpreter to create .venv.' }
foreach ($arguments in @(@('-m','pip','install','-r','requirements-lock.txt'), @('scripts/make_icon.py'), @('run.py','--selfcheck'))) {
    & $localPython @arguments
    if ($LASTEXITCODE) { throw ('Setup failed: ' + ($arguments -join ' ')) }
}
& (Join-Path $PSScriptRoot 'make_shortcut.ps1')
Write-Output 'Setup complete. Open Groundwork on your desktop.'
