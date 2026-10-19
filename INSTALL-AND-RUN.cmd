@echo off
setlocal EnableExtensions DisableDelayedExpansion
if /i "%~1"=="/?" goto help
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0source\tools\install_and_run.ps1" %*
set "result=%ERRORLEVEL%"
if not "%result%"=="0" (
  echo.
  echo Installation failed. See the error above.
  pause
)
exit /b %result%

:help
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0source\tools\install_and_run.ps1" -Help
exit /b %ERRORLEVEL%
