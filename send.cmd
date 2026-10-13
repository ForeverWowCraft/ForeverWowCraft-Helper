@echo off
setlocal
cd /d "%~dp0"
rem Sends every scan through the pipe, after each SAVE in game. Ctrl+C to stop.
rem setup.cmd has this start, minimised, when you log on to Windows; it ends by itself when another is already running.
set "PY=python"
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
"%PY%" fwch.py send --watch
if errorlevel 1 pause
