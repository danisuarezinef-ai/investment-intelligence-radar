$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
python -m pip install --upgrade pip
python -m pip install pyinstaller
if(Test-Path dist){Remove-Item dist -Recurse -Force}
if(Test-Path build){Remove-Item build -Recurse -Force}
if(Test-Path release){Remove-Item release -Recurse -Force}
New-Item -ItemType Directory -Path release -Force | Out-Null
New-Item -ItemType Directory -Path release\update-channel -Force | Out-Null
New-Item -ItemType Directory -Path assets -Force | Out-Null
$version=(Get-Content version.json -Raw -Encoding UTF8 | ConvertFrom-Json).version
if(!$version){throw 'version.json no contiene version'}

# Preserve Unicode text while synchronizing the visible app version.
$desktop=Get-Content radar_desktop.py -Raw -Encoding UTF8
$desktop=[regex]::Replace($desktop,"APP_VERSION\s*=\s*'[^']+'","APP_VERSION='$version'")
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'radar_desktop.py'),$desktop,(New-Object System.Text.UTF8Encoding($false)))

# Keep Inno Setup metadata synchronized with version.json too.
$issPath=Join-Path $PSScriptRoot 'installer\Radar.iss'
$iss=Get-Content $issPath -Raw -Encoding UTF8
$iss=[regex]::Replace($iss,'#define MyAppVersion "[^"]+"','#define MyAppVersion "'+$version+'"')
[System.IO.File]::WriteAllText($issPath,$iss,(New-Object System.Text.UTF8Encoding($false)))

Add-Type -AssemblyName System.Drawing
$bmp=New-Object System.Drawing.Bitmap 256,256
$g=[System.Drawing.Graphics]::FromImage($bmp); $g.SmoothingMode=[System.Drawing.Drawing2D.SmoothingMode]::AntiAlias; $g.Clear([System.Drawing.Color]::Transparent)
$navy=[System.Drawing.Color]::FromArgb(255,8,24,52); $cyan=[System.Drawing.Color]::FromArgb(255,27,210,255); $green=[System.Drawing.Color]::FromArgb(255,34,238,146); $muted=[System.Drawing.Color]::FromArgb(180,34,211,238)
$g.FillEllipse((New-Object System.Drawing.SolidBrush $navy),8,8,240,240); $g.DrawEllipse((New-Object System.Drawing.Pen $cyan,9),12,12,232,232); $g.DrawEllipse((New-Object System.Drawing.Pen $green,3),20,20,216,216)
foreach($r in @(42,74,106)){$g.DrawEllipse((New-Object System.Drawing.Pen $muted,2),128-$r,128-$r,$r*2,$r*2)}
$g.DrawLine((New-Object System.Drawing.Pen $muted,2),32,128,224,128); $g.DrawLine((New-Object System.Drawing.Pen $muted,2),128,32,128,224)
$g.FillPie((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(85,34,238,146))),28,28,200,200,315,44)
foreach($p in @(@(76,72),@(93,106),@(183,92),@(68,157))){$g.FillEllipse((New-Object System.Drawing.SolidBrush $green),$p[0]-5,$p[1]-5,10,10)}
$bar=New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(210,27,210,255)); $g.FillRectangle($bar,92,174,18,38); $g.FillRectangle($bar,120,158,18,54); $g.FillRectangle($bar,148,137,18,75); $g.FillRectangle((New-Object System.Drawing.SolidBrush $green),176,111,18,101)
$trend=New-Object System.Drawing.Pen $green,8; $pts=[System.Drawing.Point[]]@((New-Object System.Drawing.Point 54,187),(New-Object System.Drawing.Point 88,166),(New-Object System.Drawing.Point 116,174),(New-Object System.Drawing.Point 148,143),(New-Object System.Drawing.Point 176,151),(New-Object System.Drawing.Point 207,111)); $g.DrawLines($trend,$pts); $g.FillPolygon((New-Object System.Drawing.SolidBrush $green),[System.Drawing.Point[]]@((New-Object System.Drawing.Point 207,111),(New-Object System.Drawing.Point 190,113),(New-Object System.Drawing.Point 209,91),(New-Object System.Drawing.Point 218,119)))
$pngStream=New-Object System.IO.MemoryStream; $bmp.Save($pngStream,[System.Drawing.Imaging.ImageFormat]::Png); $png=$pngStream.ToArray(); $pngStream.Dispose(); $g.Dispose(); $bmp.Dispose()
$icoPath=Join-Path $PSScriptRoot 'assets\radar.ico'; $fs=[System.IO.File]::Create($icoPath); $bw=New-Object System.IO.BinaryWriter($fs); $bw.Write([UInt16]0); $bw.Write([UInt16]1); $bw.Write([UInt16]1); $bw.Write([Byte]0); $bw.Write([Byte]0); $bw.Write([Byte]0); $bw.Write([Byte]0); $bw.Write([UInt16]1); $bw.Write([UInt16]32); $bw.Write([UInt32]$png.Length); $bw.Write([UInt32]22); $bw.Write($png); $bw.Close(); $fs.Close()
python -m PyInstaller --noconfirm --clean --onefile --windowed --icon assets\radar.ico --name InvestmentIntelligenceRadar radar_desktop.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --icon assets\radar.ico --name RadarWorker run_worker.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --icon assets\radar.ico --name RadarUpdater radar_updater_v2.py
$updateZip='release\update-channel\RadarUpdate.zip'
Compress-Archive -Path dist\InvestmentIntelligenceRadar.exe,dist\RadarWorker.exe,dist\RadarUpdater.exe -DestinationPath $updateZip -CompressionLevel Optimal -Force
Copy-Item dist\RadarUpdater.exe release\update-channel\RadarUpdater.exe -Force
$hash=(Get-FileHash $updateZip -Algorithm SHA256).Hash.ToLowerInvariant(); $updaterHash=(Get-FileHash 'release\update-channel\RadarUpdater.exe' -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest=[ordered]@{version=$version;channel='stable';package_url='https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/updates/RadarUpdate.zip';sha256=$hash;updater_url='https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/updates/RadarUpdater.exe';updater_sha256=$updaterHash;notes='Corrige caracteres Unicode, sincroniza la version del instalador y refuerza las fuentes de datos de mercado. Mantiene el actualizador visible y conserva la base de datos.';published_at=(Get-Date).ToUniversalTime().ToString('o')}
$manifest | ConvertTo-Json | Set-Content -Path 'release\update-channel\update_manifest.json' -Encoding UTF8
$inno="${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"; if(!(Test-Path $inno)){throw 'Inno Setup 6 not found'}; & $inno installer\Radar.iss
Write-Host "Built Radar version $version"; Write-Host "Update SHA256: $hash"; Write-Host "Updater SHA256: $updaterHash"
