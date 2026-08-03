$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path `
    $PSScriptRoot `
    "start_jarvis_edge.ps1"
$Desktop = [Environment]::GetFolderPath(
    "Desktop"
)
$ShortcutPath = Join-Path `
    $Desktop `
    "Jarvis Edge.lnk"

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut(
    $ShortcutPath
)
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = (
    '-NoProfile -ExecutionPolicy Bypass -File "' +
    $StartScript +
    '"'
)
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description = (
    "Start the dedicated Jarvis Edge profile "
    + "with local CDP enabled."
)
$Shortcut.Save()

Write-Host "Created shortcut: $ShortcutPath"
