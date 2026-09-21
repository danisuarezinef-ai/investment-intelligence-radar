param(
  [string]$ProfileDir = "",
  [int]$Port = 9227,
  [int]$TimeoutSeconds = 180,
  [string]$EvidenceDir = "",
  [string]$TrialId = "",
  [string]$CanonicalOut = "",
  [string]$Provider = "chatgpt-web"
)
$ErrorActionPreference="Stop"
$base=Split-Path -Parent $MyInvocation.MyCommand.Path
$local=$env:LOCALAPPDATA
if(-not $local){$local=$env:TEMP}
if(-not $ProfileDir){$ProfileDir=Join-Path $local "CEO de IAs\browser-profile"}
if(-not $TrialId){$TrialId="TRIAL-"+(Get-Date -Format "yyyyMMdd-HHmmss")+"-"+$PID}
if(-not $EvidenceDir){$EvidenceDir=Join-Path $local ("CEO de IAs\evidence\trials\"+$TrialId)}
if(-not $CanonicalOut){$CanonicalOut=Join-Path $local "CEO de IAs\evidence\BROWSER_FIELD_STATE.json"}
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

$python=(Get-Command python.exe -ErrorAction SilentlyContinue)
if(-not $python){$python=(Get-Command py.exe -ErrorAction SilentlyContinue)}
if(-not $python){throw "Python no encontrado"}

Write-Host "=== B29-B30: campaña física única y aislada ==="
Write-Host ("Trial: "+$TrialId)
Write-Host ("Proveedor: "+$Provider)
$args=@(
  (Join-Path $base "run_field_campaign.py"),
  "--provider",$Provider,
  "--profile-dir",$ProfileDir,
  "--evidence-dir",$EvidenceDir,
  "--canonical-out",$CanonicalOut,
  "--trial-id",$TrialId,
  "--port",[string]$Port,
  "--timeout",[string]$TimeoutSeconds
)
& $python.Source @args
if($LASTEXITCODE -ne 0){throw "B29-B30 no superado; revisa FIELD_CAMPAIGN_RESULT.json de este trial"}
Write-Host "[PASS] B29-B30: BROWSER_FIELD_VERIFIED=true"
Write-Host "[LÍMITE] Sin merge, producción, compras ni APIs obligatorias."
