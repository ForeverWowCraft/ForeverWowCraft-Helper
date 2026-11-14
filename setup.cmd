@echo off
setlocal
cd /d "%~dp0"
rem Finds the game, installs the scanner addon and fetches the lists to scan. Safe to run again.
rem The zip comes with Python in python\; without it, the PC's own Python (3.10 or newer) is used.
set "PY=python"
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
"%PY%" --version >nul 2>&1
if errorlevel 1 (
  echo This zip has no Python inside, and none is installed on this PC.
  echo Either ask for the zip with Python in it, or install Python 3.10 or newer from
  echo https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH", then run setup.cmd again.
  pause
  exit /b 1
)
"%PY%" fwch.py where
echo.
echo If the folders above are wrong, set them and run setup.cmd again:
echo     setx FWC_WOW_DIR "D:\Games\World of Warcraft"
echo     setx FWC_WOW_FLAVOR "_forever_"
echo.
echo Close the game before going on: it only finds a new addon when it starts.
pause
"%PY%" fwch.py install-addon
if errorlevel 1 exit /b 1
"%PY%" fwch.py lists
if errorlevel 1 echo The lists could not be fetched; those that came with the addon are used.
"%PY%" fwch.py plans
if errorlevel 1 echo The routes could not be fetched; the helper tries again while it runs.
"%PY%" fwch.py whoami
"%PY%" fwch.py autostart
if exist "%~dp0python\pythonw.exe" (
  start "" "%~dp0python\pythonw.exe" "%~dp0fwch.py" app
) else (
  start "ForeverWowCraft Helper" /min send.cmd
)
echo.
echo Done. Start the game. /fwc shows what your professions still need, less what you have.
echo Clicking Save Prices at the auction house is optional and helps keep prices current.
echo The helper sends every scan: it is running now, an icon by the clock, and starts with Windows from now on.
