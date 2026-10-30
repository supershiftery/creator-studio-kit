@echo off
title Creator Studio setup
rem Double-click me. Installs everything (Python, FFmpeg, Node, Git, Claude Code), then opens the Studio's setup window
rem (sign in to Claude, pick your folders and music).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\install.ps1" -Launch
echo.
pause
