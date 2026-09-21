$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'CEO de IAs - DEV314 Native Transport Integrity 1.5.90'

$expected = '1.5.86-rc1-provider-session-integrity'
$target = '1.5.90-rc1-native-transport-integrity'
$manifestUrl = 'https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV314_MANIFEST_UNSIGNED.json'
$logDir = Join-Path $env:LOCALAPPDATA 'CEO de IAs\diagnostics'
$logFile = Join-Path $logDir 'DEV314_NATIVE_TRANSPORT_INTEGRITY_ACTIVACION.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Log([string]$m) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m)
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Finish([int]$code) {
    Write-Host ''
    Write-Host '============================================================'
    if ($code -eq 0) {
        Write-Host '  DEV314 / 1.5.90 PUBLICADA POR EL PROPIO CEO'
    } else {
        Write-Host '  DEV314 BLOQUEADA DE FORMA SEGURA'
        Write-Host ('  Codigo: ' + $code)
        Write-Host '  La instalacion 1.5.86 sigue intacta.'
    }
    Write-Host '============================================================'
    Write-Host ('Log: ' + $logFile)
    if ($env:CEO_ACTIVATOR_NO_PAUSE -ne '1') { Read-Host 'Pulsa ENTER para cerrar' }
    exit $code
}

try {
    Log 'Inicio DEV314.'
    $port = $null
    foreach ($p in 8765..8780) {
        try {
            $h = Invoke-RestMethod -Uri ('http://127.0.0.1:'+$p+'/api/health') -TimeoutSec 2
            Log ('Puerto '+$p+' responde con '+[string]$h.version)
            if ([string]$h.version -eq $expected) { $port=$p; break }
        } catch {}
    }
    if ($null -eq $port) {
        Log 'ERROR: no se encontro CEO 1.5.86 activo.'
        Finish 6
    }

    Log ('CEO 1.5.86 localizado en puerto '+$port)
    $body=@{manifest_url=$manifestUrl}|ConvertTo-Json -Compress
    $uri='http://127.0.0.1:'+$port+'/api/internal-release/activate-prepared'
    Log 'Solicitando verificacion, firma y publicacion interna de DEV314.'
    try {
        $r=Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $body -TimeoutSec 300
    } catch {
        Log ('ERROR HTTP: '+$_.Exception.Message)
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) { Log ('Detalle: '+$_.ErrorDetails.Message) }
        Finish 10
    }

    Log ('Respuesta publicacion: '+($r|ConvertTo-Json -Depth 8 -Compress))
    if (-not $r.ok) { Log ('ERROR: ok=false status='+[string]$r.status+' detail='+[string]$r.detail); Finish 11 }
    if ([string]$r.status -ne 'PUBLISHED') { Log ('ERROR: status='+[string]$r.status); Finish 12 }

    $visible=$false
    foreach($attempt in 1..12) {
        try {
            Start-Sleep -Seconds 2
            $u=Invoke-RestMethod -Uri ('http://127.0.0.1:'+$port+'/api/update/status?remote=1') -TimeoutSec 15
            $rv=[string]$u.remote.version
            Log ('Comprobacion remota '+$attempt+': remote='+$rv+' available='+[string]$u.available)
            if ($rv -eq $target) { $visible=$true; break }
        } catch {
            Log ('Comprobacion remota '+$attempt+' no disponible: '+$_.Exception.Message)
        }
    }

    Log 'DEV314 publicada y verificada.'
    Write-Host ''
    if ($visible) {
        Write-Host 'CEO ya ve 1.5.90 en el canal.'
        Write-Host 'En CEO pulsa Comprobar ahora y despues Instalar y reiniciar -> Confirmar.'
    } else {
        Write-Host '1.5.90 esta publicada. Pulsa Comprobar ahora dentro de CEO.'
    }
    Write-Host ''
    Write-Host 'NO generes otra clave Gemini.'
    Write-Host 'DEV314 fuerza IPv4 en httpx y usa HTTPS nativo de Windows como fallback.'
    Write-Host 'Incluye tambien DEV311, DEV312 y el cierre determinista de DEV313.'
    Write-Host ''
    Finish 0
}
catch {
    Log ('ERROR NO CONTROLADO: '+$_.Exception.Message)
    if ($_.ScriptStackTrace) { Log ('Stack: '+$_.ScriptStackTrace) }
    Finish 99
}
