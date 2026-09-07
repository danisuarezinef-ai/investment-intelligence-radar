$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
python -m pip install --upgrade pip
python -m pip install pyinstaller
if(Test-Path dist){Remove-Item dist -Recurse -Force}
if(Test-Path build){Remove-Item build -Recurse -Force}
python -m PyInstaller --noconfirm --clean --onefile --windowed --name InvestmentIntelligenceRadar radar_desktop.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --name RadarWorker run_worker.py
$inno="${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if(!(Test-Path $inno)){throw 'Inno Setup 6 not found'}
& $inno installer\Radar.iss
