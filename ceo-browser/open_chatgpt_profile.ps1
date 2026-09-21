param(
  [string]$ProfileDir = ""
)
$ErrorActionPreference="Stop"
if(-not $ProfileDir){
  $base=$env:LOCALAPPDATA
  if(-not $base){$base=$env:TEMP}
  $ProfileDir=Join-Path $base "CEO de IAs\browser-profile"
}
New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
$candidates=@(
  "$env:PROGRAMFILES\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
  "$env:PROGRAMFILES\Microsoft\Edge\Application\msedge.exe"
)
$browser=$null
foreach($p in $candidates){if($p -and (Test-Path $p)){$browser=$p;break}}
if(-not $browser){
  $cmd=Get-Command chrome.exe -ErrorAction SilentlyContinue
  if($cmd){$browser=$cmd.Source}
}
if(-not $browser){
  $cmd=Get-Command msedge.exe -ErrorAction SilentlyContinue
  if($cmd){$browser=$cmd.Source}
}
if(-not $browser){throw "Chrome/Edge not found"}
Start-Process -FilePath $browser -ArgumentList @("--user-data-dir=$ProfileDir","--no-first-run","--no-default-browser-check","https://chatgpt.com/")
Write-Host "Se abrió el perfil de navegador de CEO. Inicia sesión manualmente en ChatGPT si es necesario y cierra la ventana cuando termines."
