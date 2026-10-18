$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $project
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { & (Join-Path $project 'install.ps1') }
& $python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
$backgroundArgs = @()
if (Test-Path -LiteralPath 'assets/background.jpg') {
    $backgroundArgs = @('--add-data', 'assets/background.jpg;assets')
}
& $python -m PyInstaller --noconfirm --clean --windowed --name DailyGlimpse --collect-data opencc --add-data 'sources.json;.' @backgroundArgs app.py
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
Write-Host 'Built: dist\DailyGlimpse\DailyGlimpse.exe. Distribute the entire DailyGlimpse folder.'
