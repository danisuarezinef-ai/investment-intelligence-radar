param(
  [Parameter(Mandatory=$true)][string]$RecipePath,
  [string]$Prompt = "",
  [string]$PromptFile = "",
  [string]$ConversationUrl = "",
  [string]$ProfileDir = "",
  [int]$Port = 9227,
  [int]$TimeoutSeconds = 180,
  [switch]$NoLaunch,
  [switch]$AllowManualLogin,
  [switch]$ProbeOnly,
  [switch]$SessionProbeOnly,
  [switch]$CloseBrowserAfter
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

function Get-DevToolsVersion([int]$port) {
  try {
    return Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/json/version" -f $port) -TimeoutSec 1
  } catch {
    return $null
  }
}

function Wait-DevTools([int]$port,[int]$timeoutSeconds) {
  $deadline = [DateTime]::UtcNow.AddSeconds($timeoutSeconds)
  while([DateTime]::UtcNow -lt $deadline) {
    $v = Get-DevToolsVersion $port
    if($v -and $v.webSocketDebuggerUrl) { return $v }
    Start-Sleep -Milliseconds 250
  }
  throw "Chrome DevTools did not become available"
}

function Wait-DevToolsDown([int]$port,[int]$timeoutSeconds=20) {
  $deadline = [DateTime]::UtcNow.AddSeconds($timeoutSeconds)
  while([DateTime]::UtcNow -lt $deadline) {
    if(-not (Get-DevToolsVersion $port)) { return $true }
    Start-Sleep -Milliseconds 250
  }
  return $false
}

function Get-PageTarget([int]$port,[string]$wantedUrl,[int]$timeoutSeconds) {
  $deadline = [DateTime]::UtcNow.AddSeconds($timeoutSeconds)
  while([DateTime]::UtcNow -lt $deadline) {
    try {
      $targets = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/json" -f $port) -TimeoutSec 2
      $pages = @($targets | Where-Object { $_.type -eq "page" -and $_.webSocketDebuggerUrl })
      if($pages.Count -gt 0) {
        $match = $pages | Where-Object {
          $_.url -eq $wantedUrl -or
          ([string]$_.url).StartsWith($wantedUrl) -or
          $wantedUrl.StartsWith([string]$_.url)
        } | Select-Object -First 1
        if($match) { return $match }

        # If the exact URL is not open yet, reuse only a tab from the same origin.
        # This preserves legitimate navigation (root -> /c/... or query changes)
        # without ever falling back to restored localhost/error tabs.
        try {
          $wanted=[Uri]$wantedUrl
          $sameOrigin=$pages | Where-Object {
            try {
              $u=[Uri]([string]$_.url)
              $u.Scheme -eq $wanted.Scheme -and
              $u.Host -eq $wanted.Host -and
              $u.Port -eq $wanted.Port
            } catch { $false }
          } | Select-Object -First 1
          if($sameOrigin) { return $sameOrigin }
        } catch {}
        # Otherwise wait for the requested target instead of selecting an unrelated tab.
      }
    } catch {}
    Start-Sleep -Milliseconds 250
  }
  throw "Requested debuggable page target not found"
}

function Prune-UnrelatedRestoredTargets([int]$port,[string]$wantedUrl,[int]$settleSeconds=4) {
  # The CEO browser profile is exclusive. For external web-AI providers, remove restored
  # tabs from previous local harness runs or unrelated sites. CI localhost harnesses are
  # deliberately excluded from this cleanup.
  try { $wanted=[Uri]$wantedUrl } catch { return 0 }
  if($wanted.Host -in @("127.0.0.1","localhost")) { return 0 }

  $deadline=[DateTime]::UtcNow.AddSeconds([Math]::Max(1,$settleSeconds))
  $closed=0
  $stable=0
  while([DateTime]::UtcNow -lt $deadline -and $stable -lt 3) {
    $closedThisPass=0
    try {
      $targets=Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/json" -f $port) -TimeoutSec 2
      foreach($t in @($targets | Where-Object { $_.type -eq "page" -and $_.id })) {
        $u=[string]$t.url
        $keep=$false
        try {
          $uri=[Uri]$u
          $keep=(
            $uri.Scheme -eq $wanted.Scheme -and
            $uri.Host -eq $wanted.Host -and
            $uri.Port -eq $wanted.Port
          )
        } catch {}
        if(-not $keep) {
          try {
            Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/json/close/{1}" -f $port,$t.id) -TimeoutSec 2 | Out-Null
            $closed += 1
            $closedThisPass += 1
          } catch {}
        }
      }
    } catch {}
    if($closedThisPass -eq 0){$stable+=1}else{$stable=0}
    Start-Sleep -Milliseconds 300
  }
  return $closed
}

function Clear-RestoredTabState([string]$profileDir,[string]$wantedUrl) {
  # Keep cookies/authentication, but remove only tab/session-restore state so old
  # harness/error tabs never flash on screen when the exclusive CEO browser starts.
  try { $wanted=[Uri]$wantedUrl } catch { return 0 }
  if($wanted.Host -in @("127.0.0.1","localhost")) { return 0 }
  $removed=0
  $default=Join-Path $profileDir "Default"
  $paths=@(
    (Join-Path $default "Sessions"),
    (Join-Path $default "Last Session"),
    (Join-Path $default "Last Tabs"),
    (Join-Path $profileDir "Last Session"),
    (Join-Path $profileDir "Last Tabs")
  )
  foreach($p in $paths){
    if(Test-Path $p){
      try {
        if((Get-Item $p).PSIsContainer){
          Get-ChildItem -Force $p -ErrorAction SilentlyContinue | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
        } else {
          Remove-Item -Force $p -ErrorAction SilentlyContinue
        }
        $removed += 1
      } catch {}
    }
  }
  return $removed
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
  foreach($s in @($selectors)) { $parts += (To-JsString ([string]$s)) }
  return "[" + ($parts -join ",") + "]"
}

function Wait-DocumentReady([System.Net.WebSockets.ClientWebSocket]$ws,[int]$timeoutSeconds) {
  $deadline=[DateTime]::UtcNow.AddSeconds($timeoutSeconds)
  while([DateTime]::UtcNow -lt $deadline) {
    try {
      $ready=[string](Eval-JS $ws "document.readyState")
      if($ready -eq "interactive" -or $ready -eq "complete") { return $true }
    } catch {}
    Start-Sleep -Milliseconds 200
  }
  return $false
}

function Ensure-Navigation([System.Net.WebSockets.ClientWebSocket]$ws,[string]$targetUrl,[int]$timeoutSeconds) {
  Send-CDP $ws "Page.enable" @{} | Out-Null
  $current=[string](Eval-JS $ws "location.href")
  if($current -eq $targetUrl -or $current.StartsWith($targetUrl)) {
    Wait-DocumentReady $ws ([Math]::Min(10,$timeoutSeconds)) | Out-Null
    return @{navigated=$false;url=$current}
  }
  Send-CDP $ws "Page.navigate" @{url=$targetUrl} | Out-Null
  $deadline=[DateTime]::UtcNow.AddSeconds($timeoutSeconds)
  while([DateTime]::UtcNow -lt $deadline) {
    Start-Sleep -Milliseconds 250
    try {
      $now=[string](Eval-JS $ws "location.href")
      $ready=[string](Eval-JS $ws "document.readyState")
      if(($now -eq $targetUrl -or $now.StartsWith($targetUrl)) -and ($ready -eq "interactive" -or $ready -eq "complete")) {
        return @{navigated=$true;url=$now}
      }
    } catch {}
  }
  throw "Navigation did not reach target URL"
}

function Find-PromptInput([System.Net.WebSockets.ClientWebSocket]$ws,[object[]]$selectors,[object[]]$hints) {
  $sel=Selectors-Js @($selectors)
  $hintJs=Selectors-Js @($hints)
  $expr=@"
(() => {
 const selectors=$sel;
 const hints=$hintJs.map(x=>String(x||"").toLowerCase()).filter(Boolean);
 const roots=[document];
 for(let i=0;i<roots.length;i++){
   const root=roots[i];
   let all=[];
   try{ all=[...root.querySelectorAll("*")]; }catch(e){}
   for(const el of all){ if(el.shadowRoot) roots.push(el.shadowRoot); }
 }
 const visible=(e)=>{
   if(!e || e.disabled || e.readOnly || e.getAttribute("aria-hidden")==="true") return false;
   const s=getComputedStyle(e),r=e.getBoundingClientRect();
   return s.display!=="none" && s.visibility!=="hidden" && Number(s.opacity||1)>0 && r.width>20 && r.height>10;
 };
 const mark=(e,strategy,matched)=>{
   e.setAttribute("data-ceo-prompt-input","1");
   return {selector:"[data-ceo-prompt-input='1']",strategy:strategy,matched:matched,tag:(e.tagName||"").toLowerCase(),role:e.getAttribute("role")||"",label:e.getAttribute("aria-label")||"",placeholder:e.getAttribute("placeholder")||""};
 };
 for(const s of selectors){
   for(const root of roots){
     let e=null; try{e=root.querySelector(s)}catch(err){}
     if(visible(e)) return mark(e,"recipe-selector",s);
   }
 }
 let candidates=[];
 for(const root of roots){
   for(const s of ["textarea","input[type='text']","[contenteditable='true']","[role='textbox']"]){
     try{ candidates.push(...root.querySelectorAll(s)); }catch(e){}
   }
 }
 candidates=[...new Set(candidates)].filter(visible);
 const score=(e)=>{
   const tag=(e.tagName||"").toLowerCase();
   const role=(e.getAttribute("role")||"").toLowerCase();
   const contenteditable=(e.getAttribute("contenteditable")||"").toLowerCase();
   const semantic=[
     e.getAttribute("aria-label")||"",
     e.getAttribute("placeholder")||"",
     e.getAttribute("data-testid")||"",
     e.id||"",
     e.getAttribute("name")||""
   ].join(" ").toLowerCase();
   let n=0;
   if(tag==="textarea") n+=5;
   if(role==="textbox") n+=4;
   if(contenteditable==="true") n+=3;
   if(hints.some(h=>semantic.includes(h))) n+=8;
   if(semantic.includes("search") || semantic.includes("buscar")) n-=8;
   return n;
 };
 candidates.sort((a,b)=>score(b)-score(a));
 if(candidates.length && score(candidates[0])>=3) return mark(candidates[0],"semantic-fallback","score="+score(candidates[0]));
 return null;
})()
"@
  return Eval-JS $ws $expr
}

function Current-Responses([System.Net.WebSockets.ClientWebSocket]$ws,[object[]]$selectors) {
  $sel = Selectors-Js @($selectors)
  $expr = @"
(() => {
 const sels=$sel;
 const roots=[document];
 for(let i=0;i<roots.length;i++){
   const root=roots[i];
   let all=[];try{all=[...root.querySelectorAll("*")]}catch(e){}
   for(const el of all){if(el.shadowRoot)roots.push(el.shadowRoot)}
 }
 for(const s of sels){
   let nodes=[];
   for(const root of roots){
     try{nodes.push(...root.querySelectorAll(s))}catch(e){}
   }
   if(nodes.length){
     return nodes.map((e,i)=>({i,text:(e.innerText||e.textContent||"").trim()})).filter(x=>x.text);
   }
 }
 return [];
})()
"@
  $value = Eval-JS $ws $expr
  if($null -eq $value) { return @() }
  return @($value)
}


function Get-ComposerText([System.Net.WebSockets.ClientWebSocket]$ws,[string]$selector) {
  $sel=To-JsString $selector
  $expr=@"
(() => {
 const findMarked=(root)=>{
   try{const e=root.querySelector($sel);if(e)return e;}catch(e){}
   let all=[];try{all=[...root.querySelectorAll("*")]}catch(e){}
   for(const el of all){if(el.shadowRoot){const x=findMarked(el.shadowRoot);if(x)return x}}
   return null;
 };
 const e=findMarked(document);
 if(!e) return "";
 if(e.tagName==="TEXTAREA" || e.tagName==="INPUT") return String(e.value||"");
 if(e.getAttribute("contenteditable")==="true" || e.getAttribute("role")==="textbox"){
   return String(e.innerText||e.textContent||"");
 }
 return String(e.textContent||"");
})()
"@
  return [string](Eval-JS $ws $expr)
}

function Normalize-ComposerText([string]$value) {
  $s=[regex]::Replace([string]$value,"\\r\\n?","\\n")
  $s=$s.Replace([char]0x00A0,[char]0x20)
  $s=$s.TrimEnd([char[]]@([char]10))
  return $s
}

function Get-BusyState([System.Net.WebSockets.ClientWebSocket]$ws,[object[]]$selectors) {
  $sel=Selectors-Js @($selectors)
  $expr=@"
(() => {
 const sels=$sel;
 const roots=[document];
 for(let i=0;i<roots.length;i++){
   const root=roots[i];
   let all=[];try{all=[...root.querySelectorAll("*")]}catch(e){}
   for(const el of all){if(el.shadowRoot)roots.push(el.shadowRoot)}
 }
 const visible=(e)=>{
   if(!e) return false;
   const s=getComputedStyle(e),r=e.getBoundingClientRect();
   return s.display!=="none" && s.visibility!=="hidden" && Number(s.opacity||1)>0 && r.width>1 && r.height>1;
 };
 for(const s of sels){
   for(const root of roots){
     let nodes=[];try{nodes=[...root.querySelectorAll(s)]}catch(e){}
     if(nodes.some(visible)) return true;
   }
 }
 return false;
})()
"@
  return [bool](Eval-JS $ws $expr)
}

function Normalize-ConversationUrl([string]$url) {
  if(-not $url){ return "" }
  try {
    $u=[Uri]$url
    return $u.GetLeftPart([System.UriPartial]::Path).TrimEnd("/")
  } catch {
    return $url.TrimEnd("/")
  }
}

function Wait-StablePageUrl([System.Net.WebSockets.ClientWebSocket]$ws,[int]$timeoutSeconds=8) {
  $deadline=[DateTime]::UtcNow.AddSeconds($timeoutSeconds)
  $last=""
  $stable=0
  while([DateTime]::UtcNow -lt $deadline){
    $now=[string](Eval-JS $ws "location.href")
    if($now -and $now -eq $last){$stable+=1}else{$stable=0;$last=$now}
    if($stable -ge 2){return $now}
    Start-Sleep -Milliseconds 300
  }
  return $last
}

function Get-SessionState([System.Net.WebSockets.ClientWebSocket]$ws,[object[]]$loggedInSelectors,[object[]]$loginSelectors,[bool]$hasInput) {
  $logged=Selectors-Js @($loggedInSelectors)
  $login=Selectors-Js @($loginSelectors)
  $hasInputJs=if($hasInput){"true"}else{"false"}
  $expr=@"
(() => {
 const logged=$logged, login=$login;
 const visible=(e)=>{if(!e)return false;const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=="none"&&s.visibility!=="hidden"&&r.width>1&&r.height>1};
 const any=(sels)=>sels.some(s=>{try{return [...document.querySelectorAll(s)].some(visible)}catch(e){return false}});
 let loginVisible=any(login);
 if(!loginVisible){
   const nodes=[...document.querySelectorAll("button,a")].filter(visible).slice(0,300);
   loginVisible=nodes.some(e=>/^(log in|sign in|iniciar sesi[oó]n|acceder)$/i.test((e.innerText||e.textContent||"").trim()));
 }
 const loggedVisible=any(logged);
 if(loginVisible) return {state:"LOGIN_REQUIRED",logged_in_evidence:false,login_required_evidence:true};
 if(loggedVisible) return {state:"LOGGED_IN",logged_in_evidence:true,login_required_evidence:false};
 if($hasInputJs) return {state:"INTERACTIVE",logged_in_evidence:false,login_required_evidence:false};
 return {state:"UNKNOWN",logged_in_evidence:false,login_required_evidence:false};
})()
"@
  return Eval-JS $ws $expr
}

function Close-ControlledBrowser([System.Net.WebSockets.ClientWebSocket]$ws,[int]$port) {
  try { Send-CDP $ws "Browser.close" @{} | Out-Null } catch {}
  try { $ws.Dispose() } catch {}
  if(-not (Wait-DevToolsDown $port 20)) {
    throw "Controlled browser did not fully release CDP port after Browser.close"
  }
}

$recipe = Get-Content -Raw -Encoding UTF8 $RecipePath | ConvertFrom-Json
if(-not $recipe.url) { throw "Recipe URL missing" }
if($PromptFile) {
  if(-not (Test-Path $PromptFile)) { throw "Prompt file not found" }
  $Prompt = Get-Content -Raw -Encoding UTF8 $PromptFile
}
if(-not $ProbeOnly -and -not $SessionProbeOnly -and -not $Prompt) { throw "Prompt required" }
$targetUrl = [string]$recipe.url
if($ConversationUrl) { $targetUrl = $ConversationUrl }

if(-not $ProfileDir) {
  $base = $env:LOCALAPPDATA
  if(-not $base) { $base = $env:TEMP }
  $ProfileDir = Join-Path $base "CEO de IAs\browser-profile"
}
New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

$chrome = Find-Chrome
$existing = Get-DevToolsVersion $Port
if(-not $NoLaunch -and -not $existing) {
  [void](Clear-RestoredTabState $ProfileDir $targetUrl)
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
  [void](Prune-UnrelatedRestoredTargets $Port $targetUrl 4)
  $target = Get-PageTarget $Port $targetUrl ([Math]::Min(30,$TimeoutSeconds))
  $ws = Connect-CDP ([string]$target.webSocketDebuggerUrl)
  try {
    Send-CDP $ws "Runtime.enable" @{} | Out-Null
    $nav=Ensure-Navigation $ws $targetUrl ([Math]::Min(30,$TimeoutSeconds))

    if($ProbeOnly) {
      $pageUrl = [string](Eval-JS $ws "location.href")
      $title = [string](Eval-JS $ws "document.title")
      $row=@{
        ok=$true
        status="BROWSER_CONTROL_READY"
        provider=[string]$recipe.provider
        browser_executable=$chrome
        conversation_url=$pageUrl
        title=$title
        cdp_port=$Port
        profile_dir=$ProfileDir
        navigation_used=[bool]$nav.navigated
      }
      if($CloseBrowserAfter){Close-ControlledBrowser $ws $Port}
      Write-JsonResult $row
      exit 0
    }

    $inputSelectors=@($recipe.input_selectors)
    $hints=@($recipe.input_semantic_hints)
    if($hints.Count -eq 0){$hints=@("prompt","message","ask","chat","mensaje","pregunta","preguntar")}
    $loggedInSelectors=@($recipe.logged_in_selectors)
    $loginSelectors=@($recipe.login_required_selectors)

    if($SessionProbeOnly) {
      $waitSeconds=if($AllowManualLogin){[Math]::Min($TimeoutSeconds,300)}else{[Math]::Min($TimeoutSeconds,20)}
      $deadline=[DateTime]::UtcNow.AddSeconds($waitSeconds)
      $lastState=$null
      $candidate=$null
      while([DateTime]::UtcNow -lt $deadline){
        $candidate=Find-PromptInput $ws $inputSelectors $hints
        $state=Get-SessionState $ws $loggedInSelectors $loginSelectors ([bool]$candidate)
        $lastState=$state
        if($state.state -eq "LOGGED_IN" -or $state.state -eq "INTERACTIVE"){
          $pageUrl=[string](Eval-JS $ws "location.href")
          $row=@{
            ok=$true
            status="SESSION_READY"
            session_state=[string]$state.state
            logged_in_evidence=[bool]$state.logged_in_evidence
            provider=[string]$recipe.provider
            conversation_url=$pageUrl
            profile_dir=$ProfileDir
            input_selector=if($candidate){[string]$candidate.selector}else{""}
            input_strategy=if($candidate){[string]$candidate.strategy}else{""}
            navigation_used=[bool]$nav.navigated
          }
          if($CloseBrowserAfter){Close-ControlledBrowser $ws $Port}
          Write-JsonResult $row
          exit 0
        }
        if(-not $AllowManualLogin -and $state.state -eq "LOGIN_REQUIRED"){break}
        Start-Sleep -Milliseconds 500
      }
      $row=@{
        ok=$false
        status=if($lastState -and $lastState.state -eq "LOGIN_REQUIRED"){"LOGIN_REQUIRED"}else{"SESSION_NOT_READY"}
        session_state=if($lastState){[string]$lastState.state}else{"UNKNOWN"}
        provider=[string]$recipe.provider
        profile_dir=$ProfileDir
        detail=if($lastState -and $lastState.state -eq "LOGIN_REQUIRED"){"Manual login is required in the persistent CEO browser profile."}else{"ChatGPT session did not become interactive before timeout."}
      }
      if($CloseBrowserAfter){Close-ControlledBrowser $ws $Port}
      Write-JsonResult $row
      exit 4
    }

    $loginWait = [Math]::Min($TimeoutSeconds,45)
    if($AllowManualLogin) { $loginWait = [Math]::Min($TimeoutSeconds,300) }
    $deadline=[DateTime]::UtcNow.AddSeconds($loginWait)
    $candidate=$null
    while([DateTime]::UtcNow -lt $deadline){
      $candidate=Find-PromptInput $ws $inputSelectors $hints
      if($candidate){break}
      Start-Sleep -Milliseconds 500
    }
    if(-not $candidate) {
      $state=Get-SessionState $ws $loggedInSelectors $loginSelectors $false
      Write-JsonResult @{
        ok=$false
        status=if($state.state -eq "LOGIN_REQUIRED"){"LOGIN_REQUIRED"}else{"INPUT_NOT_FOUND"}
        provider=[string]$recipe.provider
        detail=if($state.state -eq "LOGIN_REQUIRED"){"Manual login required in CEO persistent profile."}else{"Prompt input not found using recipe selectors or semantic fallback."}
      }
      exit 4
    }

    $inputSelector=[string]$candidate.selector
    $beforeRows = @(Current-Responses $ws @($recipe.response_selectors))
    $before = $beforeRows.Count
    $userMessageSelectors=@($recipe.user_message_selectors | Where-Object { $_ })
    $beforeUserRows=if($userMessageSelectors.Count -gt 0){@(Current-Responses $ws $userMessageSelectors)}else{@()}
    $beforeUsers=$beforeUserRows.Count
    $promptJson = To-JsString $Prompt
    $inputSelJson = To-JsString $inputSelector
    $sendSel = Selectors-Js @($recipe.send_selectors)

    # B09 — focus the real composer and type through Chrome's input pipeline.
    # Do not set DOM value/textContent directly: frameworks may display that text
    # without updating the application state, leaving the real Send action disabled.
    $focusExpr = @"
(() => {
 const findMarked=(root)=>{
   try{const e=root.querySelector($inputSelJson);if(e)return e;}catch(e){}
   let all=[];try{all=[...root.querySelectorAll("*")]}catch(e){}
   for(const el of all){if(el.shadowRoot){const x=findMarked(el.shadowRoot);if(x)return x}}
   return null;
 };
 const input=findMarked(document);
 if(!input) return {ok:false,stage:"input_missing"};
 input.focus();
 return {ok:true,tag:(input.tagName||"").toLowerCase()};
})()
"@
    $focused=Eval-JS $ws $focusExpr
    if(-not $focused.ok){ throw "B09 could not focus prompt input" }

    # Clear any existing composer content with a real Ctrl+A / Backspace chord.
    Send-CDP $ws "Input.dispatchKeyEvent" @{type="rawKeyDown";key="a";code="KeyA";modifiers=2;windowsVirtualKeyCode=65;nativeVirtualKeyCode=65} | Out-Null
    Send-CDP $ws "Input.dispatchKeyEvent" @{type="keyUp";key="a";code="KeyA";modifiers=2;windowsVirtualKeyCode=65;nativeVirtualKeyCode=65} | Out-Null
    Send-CDP $ws "Input.dispatchKeyEvent" @{type="rawKeyDown";key="Backspace";code="Backspace";windowsVirtualKeyCode=8;nativeVirtualKeyCode=8} | Out-Null
    Send-CDP $ws "Input.dispatchKeyEvent" @{type="keyUp";key="Backspace";code="Backspace";windowsVirtualKeyCode=8;nativeVirtualKeyCode=8} | Out-Null

    # Input.insertText is handled by Chrome as genuine text input and reaches the
    # site's editor/framework state (unlike direct DOM assignment).
    Send-CDP $ws "Input.insertText" @{text=[string]$Prompt} | Out-Null
    Start-Sleep -Milliseconds 650

    $actualTyped=Get-ComposerText $ws $inputSelector
    $expectedNormalized = Normalize-ComposerText ([string]$Prompt)
    $actualNormalized = Normalize-ComposerText ([string]$actualTyped)
    if($actualNormalized -ne $expectedNormalized) {
      Write-JsonResult @{
        ok=$false
        status="PROMPT_INPUT_MISMATCH"
        provider=[string]$recipe.provider
        expected_chars=$Prompt.Length
        typed_chars=[string]$actualTyped.Length
        expected_normalized_chars=[int]$expectedNormalized.Length
        actual_normalized_chars=[int]$actualNormalized.Length
        detail="B09 browser-level typed prompt differed after contenteditable normalization."
      }
      exit 6
    }
    $typed=[pscustomobject]@{typed_chars=[int]$actualTyped.Length}

    # B10 — submit through trusted Chrome input; never use synthetic DOM button activation.
    # Prefer a dynamically located visible send button and dispatch a real CDP mouse
    # click to its current center. Fall back to a real CDP Enter key event.
    $sendProbeExpr = @"
(() => {
 const roots=[document];
 for(let i=0;i<roots.length;i++){
   const root=roots[i];
   let all=[];try{all=[...root.querySelectorAll("*")]}catch(e){}
   for(const el of all){if(el.shadowRoot)roots.push(el.shadowRoot)}
 }
 const visible=(e)=>{
   if(!e || e.disabled || e.getAttribute("aria-disabled")==="true") return false;
   const s=getComputedStyle(e),r=e.getBoundingClientRect();
   return s.display!=="none" && s.visibility!=="hidden" && Number(s.opacity||1)>0 && r.width>1 && r.height>1;
 };
 const diagnostics=[];
 for(const s of $sendSel){
   for(const root of roots){
     let b=null;try{b=root.querySelector(s)}catch(e){}
     if(b){
       const r=b.getBoundingClientRect();
       const item={selector:s,disabled:!!b.disabled,ariaDisabled:b.getAttribute("aria-disabled")||"",visible:visible(b),x:r.left+r.width/2,y:r.top+r.height/2};
       diagnostics.push(item);
       if(item.visible) return {found:true,selector:s,x:item.x,y:item.y,diagnostics:diagnostics};
     }
   }
 }
 return {found:false,selector:"",x:0,y:0,diagnostics:diagnostics};
})()
"@

    function Send-CdpEnter {
      Send-CDP $ws "Input.dispatchKeyEvent" @{type="rawKeyDown";key="Enter";code="Enter";windowsVirtualKeyCode=13;nativeVirtualKeyCode=13} | Out-Null
      Send-CDP $ws "Input.dispatchKeyEvent" @{type="keyUp";key="Enter";code="Enter";windowsVirtualKeyCode=13;nativeVirtualKeyCode=13} | Out-Null
    }

    function Send-CdpMouseClick([double]$x,[double]$y) {
      Send-CDP $ws "Input.dispatchMouseEvent" @{type="mouseMoved";x=$x;y=$y} | Out-Null
      Send-CDP $ws "Input.dispatchMouseEvent" @{type="mousePressed";x=$x;y=$y;button="left";clickCount=1} | Out-Null
      Send-CDP $ws "Input.dispatchMouseEvent" @{type="mouseReleased";x=$x;y=$y;button="left";clickCount=1} | Out-Null
    }

    $sendTarget=Eval-JS $ws $sendProbeExpr
    if($sendTarget.found){
      Send-CdpMouseClick ([double]$sendTarget.x) ([double]$sendTarget.y)
      $sendMethod="cdp-mouse-click"
    }else{
      Send-CdpEnter
      $sendMethod="cdp-enter"
    }

    $submissionVerified=$false
    $busySeen=$false
    $latestComposer=[string]$Prompt
    $latestUsers=$beforeUsers
    $latestResponses=$before

    function Get-SubmissionEvidence([int]$seconds) {
      $deadlineLocal=[DateTime]::UtcNow.AddSeconds([Math]::Max(1,$seconds))
      $seenBusy=$false
      $composerLocal=[string]$Prompt
      $usersLocal=$beforeUsers
      $responsesLocal=$before
      while([DateTime]::UtcNow -lt $deadlineLocal){
        Start-Sleep -Milliseconds 250
        $busyLocal=Get-BusyState $ws @($recipe.busy_selectors)
        if($busyLocal){$seenBusy=$true}
        $rowsLocal=@(Current-Responses $ws @($recipe.response_selectors))
        $userRowsLocal=if($userMessageSelectors.Count -gt 0){@(Current-Responses $ws $userMessageSelectors)}else{@()}
        $composerLocal=Get-ComposerText $ws $inputSelector
        $usersLocal=$userRowsLocal.Count
        $responsesLocal=$rowsLocal.Count
        if(
          $busyLocal -or
          $usersLocal -gt $beforeUsers -or
          $responsesLocal -gt $before -or
          ([string]$composerLocal).Length -lt [Math]::Max(1,[int]($Prompt.Length*0.5))
        ){
          return [pscustomobject]@{
            verified=$true;busy_seen=$seenBusy;composer=[string]$composerLocal;
            users=$usersLocal;responses=$responsesLocal
          }
        }
      }
      return [pscustomobject]@{
        verified=$false;busy_seen=$seenBusy;composer=[string]$composerLocal;
        users=$usersLocal;responses=$responsesLocal
      }
    }

    $evidence1=Get-SubmissionEvidence 6
    $submissionVerified=[bool]$evidence1.verified
    $busySeen=[bool]$evidence1.busy_seen
    $latestComposer=[string]$evidence1.composer
    $latestUsers=[int]$evidence1.users
    $latestResponses=[int]$evidence1.responses

    # One safe alternate action only when no signal indicates submission and the
    # original prompt remains exactly intact.
    $alternateMethod=""
    if(-not $submissionVerified){
      $composerNormalized=Normalize-ComposerText ([string]$latestComposer)
      $safeToRetry=(
        $composerNormalized -eq $expectedNormalized -and
        $latestUsers -eq $beforeUsers -and
        $latestResponses -eq $before -and
        -not $busySeen
      )
      if($safeToRetry){
        if($sendMethod -eq "cdp-mouse-click"){
          $alternateMethod="cdp-enter"
          Send-CdpEnter
        }else{
          Start-Sleep -Milliseconds 700
          $sendTarget2=Eval-JS $ws $sendProbeExpr
          if($sendTarget2.found){
            $alternateMethod="cdp-mouse-click"
            Send-CdpMouseClick ([double]$sendTarget2.x) ([double]$sendTarget2.y)
          }
        }
        if($alternateMethod){
          $sendMethod=$sendMethod + "->" + $alternateMethod
          $evidence2=Get-SubmissionEvidence 8
          $submissionVerified=[bool]$evidence2.verified
          $busySeen=([bool]$busySeen -or [bool]$evidence2.busy_seen)
          $latestComposer=[string]$evidence2.composer
          $latestUsers=[int]$evidence2.users
          $latestResponses=[int]$evidence2.responses
        }
      }
    }

    if(-not $submissionVerified){
      $diag=[ordered]@{
        send_target=$sendTarget
        final_send_method=$sendMethod
        composer_chars=[string]$latestComposer.Length
        prompt_chars=[int]$Prompt.Length
        user_messages_before=$beforeUsers
        user_messages_after=$latestUsers
        assistant_messages_before=$before
        assistant_messages_after=$latestResponses
        busy_seen=[bool]$busySeen
      }
      Write-JsonResult @{
        ok=$false
        status="PROMPT_NOT_SUBMITTED"
        provider=[string]$recipe.provider
        send_method=$sendMethod
        typed_chars=[int]$typed.typed_chars
        submission_diagnostics=$diag
        detail=("B10 saw no submission evidence after trusted Chrome input. " + ($diag | ConvertTo-Json -Compress -Depth 8))
      }
      exit 7
    }

    # B11/B12 — wait for a new assistant response and only finish after the
    # generation indicator is absent and the full response is stable.
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $last = ""
    $stable = 0
    $captured = ""
    $generationStarted=$busySeen
    $completionReason=""
    $responseIndex=-1
    while([DateTime]::UtcNow -lt $deadline) {
      Start-Sleep -Milliseconds 650
      $rows = @(Current-Responses $ws @($recipe.response_selectors))
      $busy = Get-BusyState $ws @($recipe.busy_selectors)
      if($busy){$busySeen=$true;$generationStarted=$true}
      if($rows.Count -le $before) { continue }
      $generationStarted=$true
      $text = [string]$rows[-1].text
      if(-not $text) { continue }
      $responseIndex=$rows.Count-1

      if($text -eq $last) { $stable += 1 } else { $stable = 0; $last = $text }
      if(-not $busy -and $stable -ge 2) {
        $captured = $text
        $completionReason=if($busySeen){"busy-cleared-and-response-stable"}else{"response-stable-without-busy-signal"}
        break
      }
    }

    if(-not $captured) {
      Write-JsonResult @{
        ok=$false
        status="RESPONSE_TIMEOUT"
        provider=[string]$recipe.provider
        generation_started=[bool]$generationStarted
        busy_seen=[bool]$busySeen
        detail="B11/B12 did not observe a complete stable assistant response before timeout."
      }
      exit 5
    }

    # B13 — allow a new-chat URL to settle to /c/... and prevent conversation
    # drift on continuation turns.
    $pageUrl = Wait-StablePageUrl $ws ([Math]::Min(10,$TimeoutSeconds))
    $conversationStable=[bool]$pageUrl
    $shouldLockConversation=$false
    if($ConversationUrl){
      $conversationRegex=[string]$recipe.conversation_url_regex
      if($conversationRegex){
        try{$shouldLockConversation=($ConversationUrl -match $conversationRegex)}catch{$shouldLockConversation=$false}
      }else{
        $shouldLockConversation=($ConversationUrl -match "/c/")
      }
    }
    if($shouldLockConversation){
      $wantedConversation=Normalize-ConversationUrl $ConversationUrl
      $actualConversation=Normalize-ConversationUrl $pageUrl
      if($wantedConversation -ne $actualConversation){
        Write-JsonResult @{
          ok=$false
          status="CONVERSATION_DRIFT"
          provider=[string]$recipe.provider
          requested_conversation_url=$ConversationUrl
          actual_conversation_url=$pageUrl
          detail="B13 continuation turn left the requested browser conversation."
        }
        exit 8
      }
    }

    $row=@{
      ok=$true
      status="COMPLETE"
      provider=[string]$recipe.provider
      conversation_url=$pageUrl
      response=$captured
      response_chars=$captured.Length
      response_index=$responseIndex
      typed_chars=[int]$typed.typed_chars
      send_method=$sendMethod
      submission_verified=[bool]$submissionVerified
      generation_started=[bool]$generationStarted
      busy_seen=[bool]$busySeen
      completion_reason=$completionReason
      conversation_stable=[bool]$conversationStable
      selector=$inputSelector
      input_strategy=[string]$candidate.strategy
      input_matched=[string]$candidate.matched
      navigation_used=[bool]$nav.navigated
      profile_dir=$ProfileDir
    }
    if($CloseBrowserAfter){Close-ControlledBrowser $ws $Port}
    Write-JsonResult $row
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
