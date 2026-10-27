@echo off
rem Updates your installed Creator Studio Kit to this version (keeps your setup). Run it from the NEW folder you unzipped.
cd /d "%~dp0"
python -X utf8 "%~dp0update.py" %*
echo.
pause
