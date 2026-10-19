param(
    [switch]$InstallOnly,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($Help) {
    Write-Host @'
Usage: INSTALL-AND-RUN.cmd [-InstallOnly] [-Help]

Find Python 3.13, or install it for the current user through Windows Package
Manager (winget). Create .venv, install PyInstaller there, and build LogixLab
from the current checkout. Internet access is needed for missing dependencies.

By default, launch dist\LogixLab.exe with its browser UI and tray controls.
-InstallOnly builds the executable without starting another app session.
After setup, START.cmd launches the existing build without rebuilding.

ACD conversion and the optional VMware appliance require separate setup.
'@
    exit 0
}

function Find-Python313 {
    $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $path = & $launcher.Source -3.13 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $path -and (Test-Path -LiteralPath $path)) {
                return $path
            }
        } catch { }
    }

    # Also find a fresh per-user install before PATH is refreshed in this shell.
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:ProgramFiles 'Python313\python.exe')
    )
    $command = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike '*\WindowsApps\*') {
        $candidates += $command.Source
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            try {
                $version = & $candidate -c "import sys; print('{}.{}'.format(*sys.version_info[:2]))" 2>$null
                if ($LASTEXITCODE -eq 0 -and $version -eq '3.13') {
                    return $candidate
                }
            } catch { }
        }
    }
    return $null
}

try {
    $sourceRoot = Split-Path -Parent $PSScriptRoot
    $projectRoot = Split-Path -Parent $sourceRoot
    $python = Find-Python313
    if (-not $python) {
        $winget = Get-Command winget.exe -CommandType Application -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw 'Install Python 3.13 from https://www.python.org/downloads/windows/ (include pip and the Python launcher), then run this command again. Automatic setup requires winget (Windows App Installer).'
        }
        Write-Host 'Installing Python 3.13 for the current user...'
        & $winget.Source install --id Python.Python.3.13 --exact --source winget --scope user --silent --accept-source-agreements --accept-package-agreements --disable-interactivity
        if ($LASTEXITCODE -ne 0) { throw "Python installation failed (winget exit code $LASTEXITCODE)." }
        $python = Find-Python313
        if (-not $python) { throw 'Python was installed but could not be located. Open a new terminal and run INSTALL-AND-RUN.cmd again.' }
    }

    Write-Host "Using Python: $python"
    $environmentRoot = Join-Path $projectRoot '.venv'
    $environmentPython = Join-Path $environmentRoot 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $environmentPython)) {
        Write-Host 'Creating the local build environment in .venv...'
        & $python -m venv $environmentRoot
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Check that Python includes venv and pip.' }
    }
    $environmentVersion = & $environmentPython -c "import sys; print('{}.{}'.format(*sys.version_info[:2]))"
    if ($LASTEXITCODE -ne 0 -or $environmentVersion -ne '3.13') {
        throw 'The existing .venv is not a working Python 3.13 environment. Rename it and run this command again.'
    }

    Write-Host 'Installing build dependencies in .venv...'
    & $environmentPython -m pip --disable-pip-version-check install pyinstaller
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed. Check the network connection and pip configuration.' }

    Write-Host 'Building LogixLab from the current source...'
    & (Join-Path $sourceRoot 'build.ps1') -Python $environmentPython
    $executable = Join-Path $projectRoot 'dist\LogixLab.exe'
    if (-not (Test-Path -LiteralPath $executable)) { throw 'The build did not produce dist\LogixLab.exe.' }

    if ($InstallOnly) {
        Write-Host 'Setup complete. Run START.cmd to open LogixLab.'
    } else {
        Write-Host 'Starting LogixLab. Use its tray menu or End session to quit.'
        Start-Process -FilePath $executable -WorkingDirectory $projectRoot -WindowStyle Hidden
    }
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
