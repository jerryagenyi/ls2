@echo off
rem Live interpretation test loop — run from anywhere (double-click works too).
rem Usage: live-loop.cmd [--voice fr_FR-tom-medium] [--test-tts] [--list-devices] [...]
setlocal
cd /d "%~dp0"
chcp 65001 >nul
".venv\Scripts\python.exe" "validation\scripts\live_loop.py" %*
