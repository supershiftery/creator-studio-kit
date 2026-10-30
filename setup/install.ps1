# Installs everything the studio needs on Windows 10/11, then (with -Launch) opens the Studio, whose setup window does the rest
# (Claude sign-in, your folders, music, captions).
# Safe to run again: it skips what is already there.
# Easiest: double-click SETUP.cmd in the kit folder. By hand:
#   powershell -ExecutionPolicy Bypass -File "setup\install.ps1" [-Launch]
param([switch]$Launch)
$ErrorActionPreference = "Continue"
$kit = Split-Path -Parent $PSScriptRoot
$log = Join-Path $PSScriptRoot "setup_log.txt"
try { Start-Transcript -Path $log -Force | Out-Null } catch {}

function Step($n, $text) { Write-Host ""; Write-Host "== $n/8  $text ==" -ForegroundColor Cyan }

# Windows only sees newly installed programs in NEW windows. Re-read PATH so this window sees them too (no restart needed).
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                "$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\Microsoft\WinGet\Links"
}

# Windows ships a fake "python" that only opens the Store; only count a python that really runs.
function Have-Python { try { return ((& python -c "print(42)" 2>$null) -eq "42") } catch { return $false } }
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Winget-Install($id, $extra) {
    Write-Host "Installing $id ..."
    $a = @("install", "-e", "--id", $id, "--accept-package-agreements", "--accept-source-agreements", "--silent")
    if ($extra) { $a += $extra }
    & winget @a
    Refresh-Path
}

# Files from a downloaded zip are marked "from the internet"; unmark them so Windows doesn't block the studio's scripts.
Get-ChildItem -Path $kit -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

Step 1 "Windows installer (winget)"
Refresh-Path
if (-not (Have winget)) {
    Write-Host "winget is missing. The Microsoft Store will open on 'App Installer': click Get/Update, then run SETUP.cmd again." -ForegroundColor Yellow
    Start-Process "ms-windows-store://pdp/?productid=9NBLGGH4NNS1"
    try { Stop-Transcript | Out-Null } catch {}
    exit 1
}
Write-Host "ok"

Step 2 "Programs: Python, FFmpeg, Node, Git"
if (-not (Have-Python)) { Winget-Install "Python.Python.3.12" @("--override", "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1") }
if (-not (Have ffmpeg))  { Winget-Install "Gyan.FFmpeg" }
if (-not (Have node))    { Winget-Install "OpenJS.NodeJS.LTS" }
if (-not (Have git))     { Winget-Install "Git.Git" }

Step 3 "Python packages"
if (Have-Python) {
    python -m pip install --upgrade pip --quiet
    python -m pip install -r "$kit\setup\requirements.txt"
} else { Write-Host "Python still not found - skipped (see the summary)." -ForegroundColor Yellow }

Step 4 "Browser for page captures (Playwright Chromium)"
if (Have-Python) { python -m playwright install chromium }

Step 5 "HyperFrames (motion graphics + intros)"
if (Have npx) { npx --yes hyperframes --version }

Step 6 "Whisper speech models (first time ~2 GB, takes a while)"
if (Have-Python) {
    python -c "from faster_whisper import WhisperModel; [WhisperModel(m, device='cpu', compute_type='int8') for m in ('small.en','medium.en')]; print('whisper ok')"
}

Step 7 "Claude Code"
if (-not (Have claude)) {
    Write-Host "Installing Claude Code ..."
    Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
    Refresh-Path
}

Step 8 "Desktop shortcut"
try {
    $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Creator Studio.lnk"
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = Join-Path $kit "Studio\Studio.cmd"
    $s.WorkingDirectory = Join-Path $kit "Studio"
    $s.IconLocation = Join-Path $kit "Studio\ui\studio.ico"
    $s.Save()
    Write-Host "ok: Creator Studio on your Desktop"
} catch { Write-Host "couldn't make the shortcut (not needed)" }

# ---- summary ----
Write-Host ""
Write-Host "================ CHECK ================" -ForegroundColor Cyan
$checks = [ordered]@{
    "Python"      = (Have-Python)
    "FFmpeg"      = (Have ffmpeg)
    "Node"        = (Have node)
    "Git"         = (Have git)
    "Claude Code" = (Have claude)
}
if (Have-Python) {
    $checks["Python packages"] = ((& python -c "import cv2, faster_whisper, webview; print('ok')" 2>$null) -eq "ok")
}
$bad = @()
foreach ($k in $checks.Keys) {
    if ($checks[$k]) { Write-Host ("  [ok]      " + $k) -ForegroundColor Green }
    else { Write-Host ("  [MISSING] " + $k) -ForegroundColor Red; $bad += $k }
}
$gpu = (& nvidia-smi -L 2>$null)
if ($gpu) { Write-Host "  [ok]      NVIDIA graphics card (fast renders)" -ForegroundColor Green }
else { Write-Host "  [info]    No NVIDIA card found: renders still work, just slower" }
Write-Host "Log: $log"
try { Stop-Transcript | Out-Null } catch {}

# Python + its packages run the Studio itself: without them the setup window can't open, so stop here. Anything else that's
# missing (FFmpeg, Node, Claude) gets a fix button in the Studio's setup window.
$hard = @($bad | Where-Object { $_ -in @("Python", "Python packages") })
if ($hard.Count -gt 0 -or ($bad.Count -gt 0 -and -not $Launch)) {
    Write-Host ""
    Write-Host ("Something didn't install: " + ($bad -join ", ")) -ForegroundColor Yellow
    Write-Host "Close this window and double-click SETUP.cmd once more (some installs need a fresh window)."
    Write-Host "Still missing after that? Open Claude Code in this folder and say: 'SETUP failed, read setup\setup_log.txt and fix it'."
    exit 1
}

if ($Launch) {
    Write-Host ""
    Write-Host "Installed. The Creator Studio window opens next and walks you through the rest (about 3 minutes):" -ForegroundColor Green
    Write-Host "  it checks everything, signs you in to Claude, and asks where your recordings and music are."
    Write-Host "  You can close this window."
    Start-Process -FilePath (Join-Path $kit "Studio\Studio.cmd") -WorkingDirectory (Join-Path $kit "Studio")
}
