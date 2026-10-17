$ErrorActionPreference = 'Stop'
$sourceRoot = $PSScriptRoot
$applicationRoot = Split-Path -Parent $sourceRoot
$buildRoot = Join-Path $env:TEMP 'LogixLab-build'
py -3.13 -m PyInstaller --noconfirm --onefile --windowed --name LogixLab --distpath $applicationRoot --workpath (Join-Path $buildRoot 'work') --specpath $buildRoot --add-data "${sourceRoot}\web;web" --add-data "${sourceRoot}\samples;samples" (Join-Path $sourceRoot 'launch.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
