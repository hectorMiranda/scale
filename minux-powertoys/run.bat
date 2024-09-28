@echo off
REM Launch Minux PowerToys on Windows.
REM Double-click this file, or run it from a terminal.
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 minux.py %*
) else (
  python minux.py %*
)
endlocal
