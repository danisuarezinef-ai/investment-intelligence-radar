$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'CEO de IAs - Activar DEV305 1.5.81'

$expected = '1.5.80-rc1-provider-resilience'
$manifestUrl = 'https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV305_MANIFEST_UNSIGNED.json'
$logDir = Join-Path $env:LOCALAPPDATA 'CEO de IAs\diagnostics'
$logFile = Join-Path $logDir 'DEV305_ACTIVACION_1_5_81.log'

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log([string]$Text) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text)
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Finish([int]$Code) {
    Write-Host ''
    Write-Host '============================================================'
    if ($Code -eq 0) {
        Write-Host '  1.5.81 FIRMADA Y PUBLICADA POR EL PROPIO CEO'
    } else {
        Write-Host '  ACTIVACION DEV305 BLOQUEADA DE FORMA SEGURA'
        Write-Host ('  Codigo: ' + $Code)
        Write-Host '  CEO 1.5.80 sigue activo y no se ha instalado nada.'
    }
    Write-Host '============================================================'
    Write-Host ''
    Write-Host ('Log: ' + $logFile)
    Write-Host ''
    if ($env:CEO_ACTIVATOR_NO_PAUSE -ne '1') { Read-Host 'Pulsa ENTER para cerrar' }
    exit $Code
}

try {
    Write-Log 'Inicio de activacion DEV305.'
    Write-Log ('Buscando CEO activo con version ' + $expected)

    $port = $null
    foreach ($p in 8765..8780) {
        try {
            $h = Invoke-RestMethod -Uri ('http://127.0.0.1:' + $p + '/api/health') -TimeoutSec 2
            Write-Log ('Puerto ' + $p + ' responde con version ' + [string]$h.version)
            if ([string]$h.version -eq $expected) {
                $port = $p
                break
            }
        } catch {
            # Puerto no disponible: continuar sin tratarlo como error.
        }
    }

    if ($null -eq $port) {
        Write-Log 'ERROR: no se encontro una instancia sana de CEO 1.5.80 en puertos 8765-8780.'
        Finish 6
    }

    Write-Log ('CEO 1.5.80 localizado en puerto ' + $port)
    Write-Log 'Solicitando verificacion, firma y publicacion interna de DEV305.'

    $body = @{ manifest_url = $manifestUrl } | ConvertTo-Json -Compress
    $uri = 'http://127.0.0.1:' + $port + '/api/internal-release/activate-prepared'

    try {
        $r = Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $body -TimeoutSec 300
    } catch {
        Write-Log ('ERROR HTTP/PowerShell: ' + $_.Exception.Message)
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            Write-Log ('Detalle servidor: ' + $_.ErrorDetails.Message)
        }
        Finish 10
    }

    Write-Log ('Respuesta: ' + ($r | ConvertTo-Json -Depth 8 -Compress))

    if (-not $r.ok) {
        Write-Log ('ERROR: CEO respondio ok=false. status=' + [string]$r.status + ' detail=' + [string]$r.detail)
        Finish 11
    }
    if ([string]$r.status -ne 'PUBLISHED') {
        Write-Log ('ERROR: publicacion no confirmada. status=' + [string]$r.status)
        Finish 12
    }

    Write-Log 'DEV305 publicada y verificada por CEO.'
    Write-Host ''
    Write-Host 'Ahora en CEO:'
    Write-Host '  1. Pulsa Comprobar ahora'
    Write-Host '  2. Debe aparecer 1.5.81'
    Write-Host '  3. Actualizar / Instalar y reiniciar'
    Write-Host '  4. Confirmar'
    Write-Host ''

    if ($env:CEO_ACTIVATOR_NO_BROWSER -ne '1') { try { Start-Process ('http://127.0.0.1:' + $port + '/') } catch {} }
    Finish 0
}
catch {
    Write-Log ('ERROR NO CONTROLADO: ' + $_.Exception.Message)
    if ($_.ScriptStackTrace) { Write-Log ('Stack: ' + $_.ScriptStackTrace) }
    Finish 99
}
