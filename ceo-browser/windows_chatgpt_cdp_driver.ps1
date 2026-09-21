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

function Close-ControlledBrowser([System.Net.WebSockets.ClientWebSocket]$ws) {
  try { Send-CDP $ws "Browser.close" @{} | Out-Null } catch {}
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
      if($CloseBrowserAfter){Close-ControlledBrowser $ws}
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
          if($CloseBrowserAfter){Close-ControlledBrowser $ws}
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
      if($CloseBrowserAfter){Close-ControlledBrowser $ws}
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
    $before = @(Current-Responses $ws @($recipe.response_selectors)).Count
    $promptJson = To-JsString $Prompt
    $inputSelJson = To-JsString $inputSelector
    $sendSel = Selectors-Js @($recipe.send_selectors)

    $sendExpr = @"
(() => {
 const findMarked=(root)=>{
   try{const e=root.querySelector($inputSelJson);if(e)return e;}catch(e){}
   let all=[];try{all=[...root.querySelectorAll("*")]}catch(e){}
   for(const el of all){if(el.shadowRoot){const x=findMarked(el.shadowRoot);if(x)return x}}
   return null;
 };
 const input=findMarked(document);
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
    $row=@{
      ok=$true
      status="COMPLETE"
      provider=[string]$recipe.provider
      conversation_url=$pageUrl
      response=$captured
      response_chars=$captured.Length
      selector=$inputSelector
      input_strategy=[string]$candidate.strategy
      input_matched=[string]$candidate.matched
      navigation_used=[bool]$nav.navigated
      profile_dir=$ProfileDir
    }
    if($CloseBrowserAfter){Close-ControlledBrowser $ws}
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
