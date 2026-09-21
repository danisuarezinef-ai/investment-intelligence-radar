param(
  [Parameter(Mandatory=$true)][string]$RecipePath,
  [string]$Prompt = "",
  [string]$PromptFile = "",
  [string]$ConversationUrl = "",
  [string]$ProfileDir = "",
  [int]$Port = 9227,
  [int]$TimeoutSeconds = 180,
  [switch]$NoLaunch,
  [switch]$AllowManualLogin
)

$ErrorActionPreference = "Stop"

function Write-JsonResult([hashtable]$row) {
  [Console]::Out.Write(($row | ConvertTo-Json -Depth 12 -Compress))
}

function Find-Chrome {
  $candidates = @(
    "$env:PROGRAMFILES\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
    "$env:PROGRAMFILES\Microsoft\Edge\Application\msedge.exe"
  )
  foreach($p in $candidates) {
    if($p -and (Test-Path $p)) { return $p }
  }
  $cmd = Get-Command chrome.exe -ErrorAction SilentlyContinue
  if($cmd) { return $cmd.Source }
  $cmd = Get-Command msedge.exe -ErrorAction SilentlyContinue
  if($cmd) { return $cmd.Source }
  throw "Chrome/Edge not found"
}

function Wait-DevTools([int]$port,[int]$timeoutSeconds) {
  $deadline = [DateTime]::UtcNow.AddSeconds($timeoutSeconds)
  while([DateTime]::UtcNow -lt $deadline) {
    try {
      $v = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/json/version" -f $port) -TimeoutSec 2
      if($v.webSocketDebuggerUrl) { return $v }
    } catch {}
    Start-Sleep -Milliseconds 250
  }
  throw "Chrome DevTools did not become available"
}

function Get-PageTarget([int]$port,[string]$wantedUrl,[int]$timeoutSeconds) {
  $deadline = [DateTime]::UtcNow.AddSeconds($timeoutSeconds)
  while([DateTime]::UtcNow -lt $deadline) {
    try {
      $targets = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/json" -f $port) -TimeoutSec 2
      $pages = @($targets | Where-Object { $_.type -eq "page" -and $_.webSocketDebuggerUrl })
      if($pages.Count -gt 0) {
        $match = $pages | Where-Object { $_.url -eq $wantedUrl -or $_.url.StartsWith($wantedUrl) } | Select-Object -First 1
        if($match) { return $match }
        return $pages | Select-Object -First 1
      }
    } catch {}
    Start-Sleep -Milliseconds 250
  }
  throw "No debuggable page target found"
}

function Connect-CDP([string]$wsUrl) {
  $ws = New-Object System.Net.WebSockets.ClientWebSocket
  $uri = New-Object System.Uri($wsUrl)
  $cts = New-Object Threading.CancellationTokenSource
  $cts.CancelAfter(15000)
  $ws.ConnectAsync($uri,$cts.Token).GetAwaiter().GetResult() | Out-Null
  return $ws
}

$script:nextId = 1

function Receive-CDP([System.Net.WebSockets.ClientWebSocket]$ws,[int]$wantedId,[int]$timeoutMs=15000) {
  $deadline = [DateTime]::UtcNow.AddMilliseconds($timeoutMs)
  while([DateTime]::UtcNow -lt $deadline) {
    $buffer = New-Object byte[] 65536
    $segment = New-Object 'System.ArraySegment[byte]' -ArgumentList @(,$buffer)
    $ms = New-Object IO.MemoryStream
    do {
      $remain = [int][Math]::Max(1,($deadline-[DateTime]::UtcNow).TotalMilliseconds)
      $cts = New-Object Threading.CancellationTokenSource
      $cts.CancelAfter($remain)
      try {
        $res = $ws.ReceiveAsync($segment,$cts.Token).GetAwaiter().GetResult()
      } catch {
        $ms.Dispose()
        throw "CDP receive timeout"
      }
      if($res.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
        $ms.Dispose()
        throw "CDP socket closed"
      }
      $ms.Write($buffer,0,$res.Count)
    } while(-not $res.EndOfMessage)
    $raw = [Text.Encoding]::UTF8.GetString($ms.ToArray())
    $ms.Dispose()
    try { $obj = $raw | ConvertFrom-Json } catch { continue }
    if($obj.id -eq $wantedId) { return $obj }
  }
  throw "CDP response timeout for id $wantedId"
}

function Send-CDP([System.Net.WebSockets.ClientWebSocket]$ws,[string]$method,[hashtable]$params=@{}) {
  $id = $script:nextId
  $script:nextId += 1
  $payload = @{id=$id;method=$method;params=$params} | ConvertTo-Json -Depth 30 -Compress
  $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
  $seg = New-Object 'System.ArraySegment[byte]' -ArgumentList @(,$bytes)
  $cts = New-Object Threading.CancellationTokenSource
  $cts.CancelAfter(15000)
  $ws.SendAsync($seg,[System.Net.WebSockets.WebSocketMessageType]::Text,$true,$cts.Token).GetAwaiter().GetResult() | Out-Null
  $reply = Receive-CDP $ws $id 15000
  if($reply.error) { throw ("CDP {0} failed: {1}" -f $method,($reply.error | ConvertTo-Json -Compress)) }
  return $reply.result
}

function Eval-JS([System.Net.WebSockets.ClientWebSocket]$ws,[string]$expression) {
  $r = Send-CDP $ws "Runtime.evaluate" @{
    expression=$expression
    returnByValue=$true
    awaitPromise=$true
    userGesture=$true
  }
  if($r.exceptionDetails) { throw ("JavaScript evaluation failed: " + ($r.exceptionDetails | ConvertTo-Json -Compress)) }
  return $r.result.value
}

function To-JsString([string]$value) {
  return ($value | ConvertTo-Json -Compress)
}

function Selectors-Js([object[]]$selectors) {
  $parts = @()
  foreach($s in $selectors) { $parts += (To-JsString ([string]$s)) }
  return "[" + ($parts -join ",") + "]"
}

function Wait-Input([System.Net.WebSockets.ClientWebSocket]$ws,[object[]]$selectors,[int]$timeoutSeconds) {
  $deadline = [DateTime]::UtcNow.AddSeconds($timeoutSeconds)
  $sel = Selectors-Js $selectors
  while([DateTime]::UtcNow -lt $deadline) {
    $expr = @"
(() => {
 const sels=$sel;
 for(const s of sels){ const e=document.querySelector(s); if(e && !e.disabled) return s; }
 return "";
})()
"@
    $found = [string](Eval-JS $ws $expr)
    if($found) { return $found }
    Start-Sleep -Milliseconds 500
  }
  return ""
}

function Current-Responses([System.Net.WebSockets.ClientWebSocket]$ws,[object[]]$selectors) {
  $sel = Selectors-Js $selectors
  $expr = @"
(() => {
 const sels=$sel;
 let nodes=[];
 for(const s of sels){
   const found=[...document.querySelectorAll(s)];
   if(found.length){ nodes=found; break; }
 }
 return nodes.map((e,i)=>({i,text:(e.innerText||e.textContent||"").trim()})).filter(x=>x.text);
})()
"@
  $value = Eval-JS $ws $expr
  if($null -eq $value) { return @() }
  return @($value)
}

$recipe = Get-Content -Raw -Encoding UTF8 $RecipePath | ConvertFrom-Json
if(-not $recipe.url) { throw "Recipe URL missing" }
if($PromptFile) {
  if(-not (Test-Path $PromptFile)) { throw "Prompt file not found" }
  $Prompt = Get-Content -Raw -Encoding UTF8 $PromptFile
}
if(-not $Prompt) { throw "Prompt required" }
$targetUrl = [string]$recipe.url
if($ConversationUrl) { $targetUrl = $ConversationUrl }

if(-not $ProfileDir) {
  $base = $env:LOCALAPPDATA
  if(-not $base) { $base = $env:TEMP }
  $ProfileDir = Join-Path $base "CEO de IAs\browser-profile"
}
New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

$chrome = Find-Chrome

if(-not $NoLaunch) {
  $args = @(
    "--remote-debugging-port=$Port",
    "--remote-allow-origins=*",
    "--user-data-dir=$ProfileDir",
    "--no-first-run",
    "--no-default-browser-check",
    $targetUrl
  )
  Start-Process -FilePath $chrome -ArgumentList $args | Out-Null
}

try {
  Wait-DevTools $Port ([Math]::Min(30,$TimeoutSeconds)) | Out-Null
  $target = Get-PageTarget $Port $targetUrl ([Math]::Min(30,$TimeoutSeconds))
  $ws = Connect-CDP ([string]$target.webSocketDebuggerUrl)
  try {
    Send-CDP $ws "Runtime.enable" @{} | Out-Null
    $loginWait = [Math]::Min($TimeoutSeconds,45)
    if($AllowManualLogin) { $loginWait = [Math]::Min($TimeoutSeconds,300) }
    $inputSelector = Wait-Input $ws @($recipe.input_selectors) $loginWait
    if(-not $inputSelector) {
      Write-JsonResult @{
        ok=$false
        status="LOGIN_OR_UI_REQUIRED"
        provider=[string]$recipe.provider
        detail="No prompt input was found. Log in manually or update the UI recipe."
      }
      exit 4
    }

    $before = @(Current-Responses $ws @($recipe.response_selectors)).Count
    $promptJson = To-JsString $Prompt
    $inputSelJson = To-JsString $inputSelector
    $sendSel = Selectors-Js @($recipe.send_selectors)

    $sendExpr = @"
(() => {
 const input=document.querySelector($inputSelJson);
 if(!input) return {ok:false,stage:"input_missing"};
 const prompt=$promptJson;
 input.focus();
 if(input.tagName==="TEXTAREA" || input.tagName==="INPUT"){
   const proto=Object.getPrototypeOf(input);
   const desc=Object.getOwnPropertyDescriptor(proto,"value");
   if(desc && desc.set){desc.set.call(input,prompt)}else{input.value=prompt}
 }else{
   input.textContent="";
   const range=document.createRange(); range.selectNodeContents(input); range.collapse(false);
   const selection=window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
   document.execCommand("insertText",false,prompt);
   if(!(input.innerText||input.textContent||"").trim()){input.textContent=prompt}
 }
 input.dispatchEvent(new Event("input",{bubbles:true}));
 input.dispatchEvent(new Event("change",{bubbles:true}));
 const sends=$sendSel;
 for(const s of sends){
   const b=document.querySelector(s);
   if(b && !b.disabled){ b.click(); return {ok:true,send:s}; }
 }
 input.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",code:"Enter",bubbles:true}));
 input.dispatchEvent(new KeyboardEvent("keyup",{key:"Enter",code:"Enter",bubbles:true}));
 return {ok:true,send:"enter-fallback"};
})()
"@
    $sent = Eval-JS $ws $sendExpr
    if(-not $sent.ok) { throw ("Could not send prompt: " + ($sent | ConvertTo-Json -Compress)) }

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $last = ""
    $stable = 0
    $captured = ""
    while([DateTime]::UtcNow -lt $deadline) {
      Start-Sleep -Milliseconds 800
      $rows = @(Current-Responses $ws @($recipe.response_selectors))
      if($rows.Count -le $before) { continue }
      $text = [string]$rows[-1].text
      if(-not $text) { continue }

      $busySel = Selectors-Js @($recipe.busy_selectors)
      $busyExpr = "(() => { const sels=$busySel; return sels.some(s=>!!document.querySelector(s)); })()"
      $busy = [bool](Eval-JS $ws $busyExpr)
      if($text -eq $last) { $stable += 1 } else { $stable = 0; $last = $text }
      if((-not $busy -and $stable -ge 2) -or $stable -ge 5) {
        $captured = $text
        break
      }
    }

    if(-not $captured) {
      Write-JsonResult @{
        ok=$false
        status="RESPONSE_TIMEOUT"
        provider=[string]$recipe.provider
        detail="A stable assistant response was not captured before timeout."
      }
      exit 5
    }

    $pageUrl = [string](Eval-JS $ws "location.href")
    Write-JsonResult @{
      ok=$true
      status="COMPLETE"
      provider=[string]$recipe.provider
      conversation_url=$pageUrl
      response=$captured
      response_chars=$captured.Length
      selector=$inputSelector
    }
  } finally {
    if($ws) { $ws.Dispose() }
  }
} catch {
  Write-JsonResult @{
    ok=$false
    status="ERROR"
    provider=[string]$recipe.provider
    detail=($_.Exception.GetType().Name + ": " + $_.Exception.Message)
  }
  exit 1
}
