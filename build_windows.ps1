$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
python -m pip install --upgrade pip
python -m pip install pyinstaller
if(Test-Path dist){Remove-Item dist -Recurse -Force}
if(Test-Path build){Remove-Item build -Recurse -Force}
if(Test-Path release){Remove-Item release -Recurse -Force}
New-Item -ItemType Directory -Path release -Force | Out-Null
New-Item -ItemType Directory -Path release\update-channel -Force | Out-Null

$version=(Get-Content version.json -Raw | ConvertFrom-Json).version
if(!$version){throw 'version.json no contiene version'}

python -m PyInstaller --noconfirm --clean --onefile --windowed --name InvestmentIntelligenceRadar radar_desktop.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --name RadarWorker run_worker.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --name RadarUpdater radar_updater.py

$updateZip='release\update-channel\RadarUpdate.zip'
Compress-Archive -Path dist\InvestmentIntelligenceRadar.exe,dist\RadarWorker.exe -DestinationPath $updateZip -CompressionLevel Optimal -Force
$hash=(Get-FileHash $updateZip -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest=[ordered]@{
  version=$version
  channel='stable'
  package_url='https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/updates/RadarUpdate.zip'
  sha256=$hash
  notes='Cuadros de dialogo integrados con el tema visual de Radar y actividad Cloud visible con contadores de mercado, eventos y ciclos.'
  published_at=(Get-Date).ToUniversalTime().ToString('o')
}
$manifest | ConvertTo-Json | Set-Content -Path 'release\update-channel\update_manifest.json' -Encoding UTF8

$inno="${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if(!(Test-Path $inno)){throw 'Inno Setup 6 not found'}
& $inno installer\Radar.iss

Write-Host "Built Radar version $version"
Write-Host "Update SHA256: $hash"
