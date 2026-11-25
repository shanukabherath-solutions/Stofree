@echo off
REM Convenience wrapper: runs the PowerShell build (ONEDIR + installer when Inno Setup 7 is installed).
REM Extra arguments are passed on, e.g.   build_windows.bat -OneFile -RunTests
REM See scripts\build_windows.ps1 for what it does and for all options.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_windows.ps1" %*
exit /b %ERRORLEVEL%
