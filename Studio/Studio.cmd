@echo off
rem {{STUDIO_NAME}} - desktop window (Edge WebView2). Closing it during a build asks to keep building hidden; running this again brings the window back.
cd /d "%~dp0"
start "" /min pythonw -X utf8 "%~dp0app\main.py"
