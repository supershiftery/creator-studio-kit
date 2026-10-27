# Starts the drop-folder watcher at every Windows sign-in (Startup folder shortcut, no admin needed), and starts it now.
# Usage: powershell -ExecutionPolicy Bypass -File install_watcher.ps1 [-Inbox "{{PROJECTS_ROOT}}"] [-Uninstall]
param([string]$Inbox = "{{PROJECTS_ROOT}}", [switch]$Uninstall)

$pyw = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\pythonw.exe"
$script = Join-Path $PSScriptRoot "watcher.py"
$lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "AI Editing Watcher.lnk"

if ($Uninstall) {
    if (Test-Path $lnk) { Remove-Item $lnk -Confirm:$false }
    $pidFile = Join-Path $Inbox "_watcher\watcher.pid"
    if (Test-Path $pidFile) { Stop-Process -Id ([int](Get-Content $pidFile)) -ErrorAction SilentlyContinue -Confirm:$false }
    "Watcher removed."
    return
}

$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = $pyw
$s.Arguments = "`"$script`" `"$Inbox`""
$s.WorkingDirectory = $PSScriptRoot
$s.Description = "Edits product review videos dropped in $Inbox"
$s.Save()
Start-Process -FilePath $pyw -ArgumentList "`"$script`" `"$Inbox`"" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
"Watcher installed: $lnk"
