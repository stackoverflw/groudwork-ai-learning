# Create per-user shortcuts without elevation or altering other projects.
param([switch]$Startup)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$folder = if ($Startup) { [Environment]::GetFolderPath('Startup') } else { [Environment]::GetFolderPath('Desktop') }
$linkName = if ($Startup) { 'Groundwork Reminder.lnk' } else { 'Groundwork.lnk' }
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $folder $linkName))
$shortcut.TargetPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$shortcut.Arguments = '"' + (Join-Path $projectRoot 'run.py') + '"' + $(if ($Startup) { ' --reminder' } else { '' })
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = Join-Path $projectRoot 'app\web\groundwork.ico'
$shortcut.Save()
Write-Output (Join-Path $folder $linkName)
