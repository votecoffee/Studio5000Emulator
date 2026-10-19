param([string]$Python)

$ErrorActionPreference = 'Stop'
$pythonCommand = 'py'
$pythonArguments = @('-3.13')
if ($Python) {
    $pythonCommand = $Python
    $pythonArguments = @()
}
$sourceRoot = $PSScriptRoot
$applicationRoot = Split-Path -Parent $sourceRoot
$distRoot = Join-Path $applicationRoot 'dist'
$buildRoot = Join-Path $env:TEMP 'LogixLab-build'
New-Item -ItemType Directory -Force $buildRoot | Out-Null
$versionFile = Join-Path $buildRoot 'version.txt'
& $pythonCommand @pythonArguments -c "import sys; sys.path.insert(0, sys.argv[1]); from logixlab.versioning import write_windows_resource; write_windows_resource(sys.argv[2])" $sourceRoot $versionFile
if ($LASTEXITCODE -ne 0) { throw 'Version metadata generation failed' }
& $pythonCommand @pythonArguments -m PyInstaller --noconfirm --onefile --windowed --name LogixLab --version-file $versionFile --distpath $distRoot --workpath (Join-Path $buildRoot 'work') --specpath $buildRoot --add-data "${sourceRoot}\web;web" --add-data "${sourceRoot}\samples\*.L5X;samples" (Join-Path $sourceRoot 'launch.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
