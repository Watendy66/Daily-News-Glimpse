param([string]$Python = '')
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $project
$venvPython = Join-Path $project '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    $candidates = @()
    if ($Python) {
        $candidates += @{ Exe = $Python; Args = @() }
    } else {
        if ($env:CONDA_PREFIX) {
            $candidates += @{ Exe = (Join-Path $env:CONDA_PREFIX 'python.exe'); Args = @() }
        }
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $candidates += @{ Exe = 'py'; Args = @('-3.12') }
            $candidates += @{ Exe = 'py'; Args = @('-3.11') }
        }
        if (Get-Command python -ErrorAction SilentlyContinue) {
            $candidates += @{ Exe = 'python'; Args = @() }
        }
    }
    $selected = $null
    foreach ($candidate in $candidates) {
        $exe = $candidate.Exe
        $pythonArgs = $candidate.Args
        try {
            & $exe @pythonArgs -c 'import sys; sys.exit(0 if sys.version_info[:2] in [(3,11),(3,12)] else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { $selected = $candidate; break }
        } catch { }
    }
    if (-not $selected) { throw 'Python 3.11 or 3.12 not found. Activate a Conda environment or pass -Python <path-to-python.exe>.' }
    $exe = $selected.Exe
    $pythonArgs = $selected.Args
    & $exe @pythonArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create .venv.' }
}
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the network and retry.' }
Write-Host 'Installed. Double-click run.bat to start Daily Glimpse.'
