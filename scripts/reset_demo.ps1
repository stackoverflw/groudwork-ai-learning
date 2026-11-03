# Build demo records only after an explicit reset argument; preserve a full snapshot.
param([switch]$ConfirmReset)
$ErrorActionPreference = 'Stop'
if (!$ConfirmReset) { throw 'Stop the app, then pass -ConfirmReset. Existing records will be backed up first.' }
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& '.\.venv\Scripts\python.exe' 'scripts/demo.py'
if ($LASTEXITCODE) { throw 'Demo reset failed' }
