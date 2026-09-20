$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'CEO de IAs - Publicar Autonomy Bootstrap 1.5.82'

$expected = '1.5.80-rc1-provider-resilience'
$target = '1.5.82-rc1-autonomy-bootstrap'
$releaseSequence = 306
$releaseId = 'dev306-1.5.82-rc1-autonomy-bootstrap'
$manifestUrl = 'https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV306_MANIFEST_UNSIGNED.json'
$activeManifestUrl = 'https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/manifest.json'

$logDir = Join-Path $env:LOCALAPPDATA 'CEO de IAs\diagnostics'
$logFile = Join-Path $logDir 'DEV306_AUTONOMY_BOOTSTRAP_ACTIVACION.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function L([string]$Text) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text)
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Finish([int]$Code) {
    Write-Host ''
    Write-Host '============================================================'
    if ($Code -eq 0) {
        Write-Host '  AUTONOMY BOOTSTRAP 1.5.82 PUBLICADO'
    } else {
        Write-Host '  ACTIVACION BLOQUEADA DE FORMA SEGURA'
        Write-Host ('  Codigo: ' + $Code)
        Write-Host '  La instalacion actual permanece sin cambios.'
    }
    Write-Host '============================================================'
    Write-Host ''
    Write-Host ('Log: ' + $logFile)
    Write-Host ''
    if ($env:CEO_ACTIVATOR_NO_PAUSE -ne '1') { Read-Host 'Pulsa ENTER para cerrar' }
    exit $Code
}

try {
    L 'Inicio DEV306 Autonomy Bootstrap.'

    try {
        $remote = Invoke-RestMethod -Uri ($activeManifestUrl + '?nocache=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) -TimeoutSec 20
        if ([int]$remote.release_sequence -eq $releaseSequence -and [string]$remote.release_id -eq $releaseId) {
            L ('DEV306 ya estaba publicado. Version remota: ' + [string]$remote.version)
            Finish 0
        }
    } catch {
        L ('Aviso: no se pudo comprobar previamente el manifest remoto: ' + $_.Exception.Message)
    }

    $port = $null
    foreach ($p in 8765..8780) {
        try {
            $h = Invoke-RestMethod -Uri ('http://127.0.0.1:' + $p + '/api/health') -TimeoutSec 2
            L ('Puerto ' + $p + ' responde con version ' + [string]$h.version)
            if ([string]$h.version -eq $expected) {
                $port = $p
                break
            }
        } catch {}
    }

    if ($null -eq $port) {
        L ('ERROR: no se encontro CEO activo en version ' + $expected)
        Finish 6
    }

    L ('CEO ' + $expected + ' localizado en puerto ' + $port)
    L 'Solicitando al PreparedReleaseBridge interno verificar, firmar y publicar DEV306.'

    $body = @{ manifest_url = $manifestUrl } | ConvertTo-Json -Compress
    $uri = 'http://127.0.0.1:' + $port + '/api/internal-release/activate-prepared'

    try {
        $r = Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $body -TimeoutSec 300
    } catch {
        L ('ERROR HTTP/PowerShell: ' + $_.Exception.Message)
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            L ('Detalle servidor: ' + $_.ErrorDetails.Message)
        }
        Finish 10
    }

    L ('Respuesta: ' + ($r | ConvertTo-Json -Depth 8 -Compress))

    if (-not $r.ok) {
        L ('ERROR: CEO respondio ok=false. status=' + [string]$r.status + ' detail=' + [string]$r.detail)
        Finish 11
    }

    if ([string]$r.status -ne 'PUBLISHED') {
        L ('ERROR: publicacion no confirmada. status=' + [string]$r.status)
        Finish 12
    }

    L ('DEV306 publicada y verificada. Version objetivo: ' + $target)
    Write-Host ''
    Write-Host 'Ahora en CEO:'
    Write-Host '  1. Pulsa Comprobar ahora'
    Write-Host '  2. Debe aparecer 1.5.82 Autonomy Bootstrap'
    Write-Host '  3. Pulsa Actualizar / Instalar y reiniciar'
    Write-Host '  4. Confirma la instalacion'
    Write-Host ''

    if ($env:CEO_ACTIVATOR_NO_BROWSER -ne '1') {
        try { Start-Process ('http://127.0.0.1:' + $port + '/') } catch {}
    }
    Finish 0
}
catch {
    L ('ERROR NO CONTROLADO: ' + $_.Exception.Message)
    if ($_.ScriptStackTrace) { L ('Stack: ' + $_.ScriptStackTrace) }
    Finish 99
}
