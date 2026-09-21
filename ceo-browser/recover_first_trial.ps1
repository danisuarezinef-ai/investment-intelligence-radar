param(
  [string]$ProfileDir = ""
)
$ErrorActionPreference="Stop"
if(-not $ProfileDir){
  $local=$env:LOCALAPPDATA
  if(-not $local){$local=$env:TEMP}
  $ProfileDir=Join-Path $local "CEO de IAs\browser-profile"
}
$resolved=[IO.Path]::GetFullPath($ProfileDir)
Write-Host "Recuperacion segura de la prueba CEO."
Write-Host "Perfil protegido: $resolved"
$targets=Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -and
  ($_.Name -match 'chrome|msedge') -and
  $_.CommandLine.ToLower().Contains($resolved.ToLower())
}
if(-not $targets){
  Write-Host "[OK] No hay navegadores de la prueba que cerrar."
  exit 0
}
foreach($p in $targets){
  Write-Host ("Cerrando proceso de LAB PID={0} {1}" -f $p.ProcessId,$p.Name)
  Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
}
Write-Host "[OK] Solo se cerraron procesos que usaban el perfil exclusivo de CEO."
Write-Host "[OK] Evidencias y CEO estable no se han tocado."
