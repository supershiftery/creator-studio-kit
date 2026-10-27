@echo off
rem Fallback: run the studio in your default browser (no native window).
cd /d "%~dp0"
start "" /min pythonw -X utf8 "%~dp0app\main.py" --browser
