# Installs what the studio needs on Windows 10/11. Safe to run again (it skips what is already there).
# Run from PowerShell:  powershell -ExecutionPolicy Bypass -File "setup\install.ps1"
$ErrorActionPreference = "Continue"
$kit = Split-Path -Parent $PSScriptRoot

function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

Write-Host "== 1/5 Programs (winget) =="
if (-not (Have python)) { winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements }
if (-not (Have ffmpeg)) { winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements }
if (-not (Have node))   { winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements }
if (-not (Have git))    { winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements }
Write-Host "If anything was just installed, CLOSE this window, open a new PowerShell and run this script again."

Write-Host "== 2/5 Python packages =="
python -m pip install --upgrade pip
python -m pip install -r "$kit\setup\requirements.txt"

Write-Host "== 3/5 Browser for page captures (Playwright Chromium) =="
python -m playwright install chromium

Write-Host "== 4/5 HyperFrames (motion graphics + intros) =="
npx --yes hyperframes --version

Write-Host "== 5/5 Whisper models (first download, ~2 GB) =="
python -c "from faster_whisper import WhisperModel; [WhisperModel(m, device='cpu', compute_type='int8') for m in ('small.en','medium.en')]; print('whisper ok')"

Write-Host ""
Write-Host "Checks:"
ffmpeg -hide_banner -encoders 2>$null | Select-String "h264_nvenc|libx264"
nvidia-smi -L 2>$null
Write-Host "Done. Next: open Claude Code in this folder and paste the MASTER PROMPT."
