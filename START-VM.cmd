@echo off
cd /d "%~dp0"
if not exist "%~dp0.local\vmware\appliance\appliance.json" (
  echo Prepare the optional VMware appliance first. See docs\vmware-appliance.md.
  exit /b 1
)
start "" pyw -3.13 "%~dp0source\tools\vmware_appliance.py" start
