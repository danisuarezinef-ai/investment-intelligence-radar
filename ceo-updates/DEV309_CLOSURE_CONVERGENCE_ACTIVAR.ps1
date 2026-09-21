$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'CEO de IAs - DEV309 Closure Convergence 1.5.85'

$expected = '1.5.84-rc1-executable-route-integrity'
$target = '1.5.85-rc1-closure-convergence'
$manifestUrl = 'https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV309_MANIFEST_UNSIGNED.json'
$logDir = Join-Path $env:LOCALAPPDATA 'CEO de IAs\diagnostics'
$logFile = Join-Path $logDir 'DEV309_CLOSURE_CONVERGENCE_ACTIVACION.log'
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
        Write-Host '  DEV309 / 1.5.85 PUBLICADA POR EL PROPIO CEO'
    } else {
        Write-Host '  DEV309 BLOQUEADA DE FORMA SEGURA'
        Write-Host ('  Codigo: ' + $code)
        Write-Host '  La instalacion 1.5.84 sigue intacta.'
    }
    Write-Host '============================================================'
    Write-Host ('Log: ' + $logFile)
    if ($env:CEO_ACTIVATOR_NO_PAUSE -ne '1') { Read-Host 'Pulsa ENTER para cerrar' }
    exit $code
}

try {
    Log 'Inicio DEV309.'
    $port = $null
    foreach ($p in 8765..8780) {
        try {
            $h = Invoke-RestMethod -Uri ('http://127.0.0.1:'+$p+'/api/health') -TimeoutSec 2
            Log ('Puerto '+$p+' responde con '+[string]$h.version)
            if ([string]$h.version -eq $expected) { $port=$p; break }
        } catch {}
    }
    if ($null -eq $port) {
        Log 'ERROR: no se encontro CEO 1.5.84 activo.'
        Finish 6
    }

    Log ('CEO 1.5.84 localizado en puerto '+$port)
    $body=@{manifest_url=$manifestUrl}|ConvertTo-Json -Compress
    $uri='http://127.0.0.1:'+$port+'/api/internal-release/activate-prepared'
    Log 'Solicitando verificacion, firma y publicacion interna de DEV309.'
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

    Log 'DEV309 publicada y verificada.'
    Write-Host ''
    if ($visible) {
        Write-Host 'CEO ya ve 1.5.85 en el canal.'
        Write-Host 'En CEO pulsa Comprobar ahora y despues Actualizar / Instalar y reiniciar -> Confirmar.'
    } else {
        Write-Host '1.5.85 esta publicada, pero esta instancia aun no la refleja.'
        Write-Host 'Cierra y abre CEO una vez; despues pulsa Comprobar ahora e instala 1.5.85.'
    }
    Write-Host ''
    Write-Host 'Tras reiniciar, NO crees otro objetivo.'
    Write-Host 'DEV309 debe migrar el audit historico #173 a un cierre nuevo y acotado.'
    Write-Host ''

    if ($env:CEO_ACTIVATOR_NO_BROWSER -ne '1') {
        try { Start-Process ('http://127.0.0.1:'+$port+'/') } catch {}
    }
    Finish 0
}
catch {
    Log ('ERROR NO CONTROLADO: '+$_.Exception.Message)
    if ($_.ScriptStackTrace) { Log ('Stack: '+$_.ScriptStackTrace) }
    Finish 99
}
