$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='CEO de IAs - Recuperar instalacion DEV310'

$source='1.5.85-rc1-closure-convergence'
$target='1.5.86-rc1-provider-session-integrity'
$logDir=Join-Path $env:LOCALAPPDATA 'CEO de IAs\diagnostics'
$logFile=Join-Path $logDir 'RECUPERAR_INSTALACION_DEV310.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Log([string]$m){
  $line=('['+(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+'] '+$m)
  Write-Host $line
  Add-Content -Path $logFile -Value $line -Encoding UTF8
}
function Find-Ceo([string]$version){
  foreach($p in 8765..8780){
    try{
      $h=Invoke-RestMethod -Uri ('http://127.0.0.1:'+$p+'/api/health') -TimeoutSec 2
      if([string]$h.version -eq $version -and $h.ok){return $p}
    }catch{}
  }
  return $null
}
function Open-App([string]$url){
  $pf86=[Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
  $candidates=@(
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $pf86 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $pf86 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')
  )
  foreach($exe in $candidates){
    if($exe -and (Test-Path $exe)){
      Start-Process -FilePath $exe -ArgumentList @('--app='+$url,'--start-maximized')
      return $true
    }
  }
  Start-Process $url
  return $false
}

try{
  Log 'Buscando CEO 1.5.85 activo.'
  $port=Find-Ceo $source
  if($null -eq $port){
    $already=Find-Ceo $target
    if($null -ne $already){
      Log ('DEV310 ya esta activo en puerto '+$already+'.')
      Open-App ('http://127.0.0.1:'+$already) | Out-Null
      exit 0
    }
    throw 'No se encontro CEO 1.5.85 ni 1.5.86 activo. Deja abierta la pestaña actual de CEO y vuelve a ejecutar este archivo.'
  }

  $base='http://127.0.0.1:'+$port
  Log ('CEO origen localizado: '+$base)
  $status=Invoke-RestMethod -Uri ($base+'/api/update/status') -TimeoutSec 20
  $row=$null
  foreach($x in @($status.staged)){
    if([string]$x.version -eq $target -and -not $x.installed -and -not $x.rolled_back -and -not $x.preflight_failed){
      $row=$x; break
    }
  }
  if($null -eq $row){
    throw 'DEV310 no aparece como preparada. No se descargara nada automaticamente desde este recuperador.'
  }

  Log ('Paquete ya preparado y verificado: '+$target)
  Write-Host ''
  Write-Host 'La descarga ya termino. Este paso solo reanuda la instalacion preparada.'
  Write-Host 'No se vuelve a descargar el paquete.'
  Write-Host ''
  $answer=$env:CEO_RECOVERY_CONFIRM
  if(-not $answer){$answer=Read-Host 'Escribe SI para instalar y reiniciar DEV310'}
  if([string]$answer -notmatch '^(?i:si|sí|yes|y)$'){
    Log 'Instalacion cancelada por el usuario.'
    exit 2
  }

  Log 'Confirmacion humana recibida. Iniciando preflight + instalacion.'
  $body=@{version=$target;confirm=$true}|ConvertTo-Json -Compress
  $r=Invoke-RestMethod -Method Post -Uri ($base+'/api/update/install') -ContentType 'application/json' -Body $body -TimeoutSec 120
  Log ('Respuesta de instalacion: '+($r|ConvertTo-Json -Depth 6 -Compress))

  Write-Host ''
  Write-Host 'CEO esta reiniciando. Esperando la nueva version...'
  $newPort=$null
  foreach($i in 1..90){
    Start-Sleep -Seconds 1
    $newPort=Find-Ceo $target
    if($null -ne $newPort){break}
  }
  if($null -eq $newPort){
    throw 'La nueva version no aparecio dentro de 90 s. Revisa el log de reinicio/rollback de CEO.'
  }

  $url='http://127.0.0.1:'+$newPort
  Log ('DEV310 activo: '+$url)
  Open-App $url | Out-Null
  Write-Host ''
  Write-Host 'OK: DEV310 esta activo y se ha solicitado apertura en modo app.'
  Write-Host 'Puedes cerrar la pestaña normal de Chrome cuando veas la ventana de CEO.'
  exit 0
}catch{
  Log ('ERROR: '+$_.Exception.Message)
  Write-Host ''
  Write-Host 'La version actual se mantiene intacta.'
  if($env:CEO_RECOVERY_NO_PAUSE -ne '1'){Read-Host 'Pulsa ENTER para cerrar'}
  exit 7
}