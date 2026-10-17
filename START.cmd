@echo off
cd /d "%~dp0"
if not exist "%~dp0dist\LogixLab.exe" (
  echo Build the app first with source\build.ps1, or run source\run-from-source.cmd.
  exit /b 1
)
start "" "%~dp0dist\LogixLab.exe"
