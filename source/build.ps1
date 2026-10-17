$ErrorActionPreference = 'Stop'
$sourceRoot = $PSScriptRoot
$applicationRoot = Split-Path -Parent $sourceRoot
$distRoot = Join-Path $applicationRoot 'dist'
$buildRoot = Join-Path $env:TEMP 'LogixLab-build'
py -3.13 -m PyInstaller --noconfirm --onefile --windowed --name LogixLab --distpath $distRoot --workpath (Join-Path $buildRoot 'work') --specpath $buildRoot --add-data "${sourceRoot}\web;web" --add-data "${sourceRoot}\samples\*.L5X;samples" (Join-Path $sourceRoot 'launch.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
