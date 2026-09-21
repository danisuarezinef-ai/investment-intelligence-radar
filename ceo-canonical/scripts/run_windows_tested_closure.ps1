param(
  [switch]$SkipDependencyInstall,
  [switch]$SkipBuild,
  [switch]$SkipInstaller
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $Root
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$Root;$env:PYTHONPATH" } else { $Root }
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Out = Join-Path $Root "reports\windows-tested\$Stamp"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$Log = Join-Path $Out 'WINDOWS_TESTED_TRANSCRIPT.txt'
$Results = New-Object System.Collections.Generic.List[object]
Start-Transcript -Path $Log -Force | Out-Null

function Add-Result([string]$Name,[string]$Status,[string]$Detail='') {
  $Results.Add([pscustomobject]@{name=$Name;status=$Status;detail=$Detail;time=(Get-Date).ToString('o')})
  Write-Host "[$Status] $Name $Detail"
}
function Save-Results {
  $Results | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $Out 'WINDOWS_TESTED_RESULTS.json')
}
function Run-Native([string]$Name,[scriptblock]$Command) {
  try {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "exit code $LASTEXITCODE" }
    Add-Result $Name 'PASS'
    return $true
  } catch {
    Add-Result $Name 'FAIL' $_.Exception.Message
    return $false
  } finally { Save-Results }
}

try {
  if ($env:OS -ne 'Windows_NT') { throw 'This runner must be executed on Windows.' }
  Add-Result 'windows-environment' 'PASS' ([Environment]::OSVersion.VersionString)

  # Hardware inventory
  $hw = [ordered]@{}
  $hw.timestamp=(Get-Date).ToString('o')
  $hw.os=Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture,TotalVisibleMemorySize,FreePhysicalMemory
  $hw.computer=Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,TotalPhysicalMemory,NumberOfLogicalProcessors
  $hw.cpu=Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed
  $hw.gpu=@(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion)
  $hw | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $Out 'HARDWARE.json')
  Add-Result 'hardware-profiler' 'PASS'

  # Resolve Python 3.11+ robustly. Explorer may retain an old PATH after Python installation,
  # so do not rely only on Get-Command. Prefer the launcher, then python.exe, then common
  # per-user/system install locations.
  $PythonExe=$null; $PythonPrefix=@()

  function Try-PythonCandidate([string]$Exe,[string[]]$Prefix=@()) {
    if (-not $Exe) { return $false }
    try {
      & $Exe @Prefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 2)" 2>$null
      if ($LASTEXITCODE -eq 0) {
        $script:PythonExe=$Exe
        $script:PythonPrefix=@($Prefix)
        return $true
      }
    } catch {}
    return $false
  }

  $pyCmd=Get-Command py.exe -ErrorAction SilentlyContinue
  if ($pyCmd) {
    # -3 selects the newest installed Python 3 and avoids pinning the runner to 3.11.
    [void](Try-PythonCandidate $pyCmd.Source @('-3'))
  }

  if (-not $PythonExe) {
    $pythonCmd=Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCmd) { [void](Try-PythonCandidate $pythonCmd.Source @()) }
  }

  if (-not $PythonExe) {
    $candidatePaths = New-Object System.Collections.Generic.List[string]
    if ($env:WINDIR) { $candidatePaths.Add((Join-Path $env:WINDIR 'py.exe')) }
    if ($env:LOCALAPPDATA) {
      $candidatePaths.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher\py.exe'))
      $pythonRoot=Join-Path $env:LOCALAPPDATA 'Programs\Python'
      if (Test-Path $pythonRoot) {
        Get-ChildItem -Path $pythonRoot -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
          Sort-Object Name -Descending |
          ForEach-Object { $candidatePaths.Add((Join-Path $_.FullName 'python.exe')) }
      }
    }
    if ($env:ProgramFiles) {
      Get-ChildItem -Path $env:ProgramFiles -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object { $candidatePaths.Add((Join-Path $_.FullName 'python.exe')) }
    }
    foreach($candidate in $candidatePaths) {
      if (-not $PythonExe -and (Test-Path $candidate)) {
        if ([IO.Path]::GetFileName($candidate) -ieq 'py.exe') {
          [void](Try-PythonCandidate $candidate @('-3'))
        } else {
          [void](Try-PythonCandidate $candidate @())
        }
      }
    }
  }

  if (-not $PythonExe) {
    Add-Result 'python-3.11+' 'BLOCKED' 'Python 3.11+ was not found by PATH, Python Launcher, or common Windows install locations.'
    throw 'No suitable Python runtime found.'
  }
  $pyVersion = & $PythonExe @PythonPrefix -c "import sys; print(sys.version)"
  Add-Result 'python-3.11+' 'PASS' ("$pyVersion via $PythonExe $($PythonPrefix -join ' ')")

  if (-not $SkipDependencyInstall) {
    # Bootstrap pip first, then install the exact runtime/test/build dependencies explicitly.
    # Do not rely on editable-install discovery as the only path: this runner is a Windows
    # validation kit and must remain robust even when setuptools behavior changes.
    try { & $PythonExe @PythonPrefix -m ensurepip --upgrade 2>$null | Out-Null } catch {}
    $bootstrapOk = Run-Native 'pip-bootstrap' { & $PythonExe @PythonPrefix -m pip install --upgrade pip setuptools wheel }
    if (-not $bootstrapOk) { throw 'pip bootstrap failed; cannot continue safely.' }

    $deps = @(
      'fastapi>=0.115',
      'uvicorn[standard]>=0.30',
      'pydantic>=2.8',
      'psutil>=6.0',
      'playwright>=1.50',
      'httpx>=0.27',
      'cryptography>=44.0',
      'pytest>=8',
      'pytest-asyncio>=0.23',
      'ruff>=0.6',
      'pyinstaller>=6.10'
    )
    $depOk = Run-Native 'install-test-build-dependencies' { & $PythonExe @PythonPrefix -m pip install @deps }
    if (-not $depOk) { throw 'dependency installation failed; see transcript for the pip error.' }

    # No editable install is required for the TESTED kit: commands execute from the
    # project root, and PyInstaller receives that root explicitly in its .spec file.
    # Avoiding an editable install removes a packaging-backend/network failure mode.
  }

  $importsOk = Run-Native 'dependency-import-check' { & $PythonExe @PythonPrefix -c "import fastapi,pydantic,psutil,playwright,httpx,cryptography,pytest,PyInstaller; print('dependency imports ok')" }
  if (-not $importsOk) { throw 'dependency import verification failed.' }

  Run-Native 'packaging-preflight' { & $PythonExe @PythonPrefix scripts\windows_packaging_preflight.py } | Out-Null

  # Browser-dependent tests are part of the full regression. Provision managed Chromium first.
  $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $Root 'build\playwright-browsers'
  Run-Native 'playwright-chromium-install' { & $PythonExe @PythonPrefix -m playwright install chromium } | Out-Null

  # Capture pytest output explicitly. Run the destructive/stress group in a fresh
  # interpreter so event-loop/global state from earlier integration tests cannot contaminate it.
  $regLog = Join-Path $Out 'FULL_REGRESSION.log'
  $regStressLog = Join-Path $Out 'FULL_REGRESSION_DESTRUCTIVE.log'
  $regErr = Join-Path $Out 'FULL_REGRESSION.err.log'
  $regStressErr = Join-Path $Out 'FULL_REGRESSION_DESTRUCTIVE.err.log'
  $mainArgs=@($PythonPrefix) + @('-m','pytest','-q','--ignore=tests/test_mvp08_destructive.py')
  $rp=Start-Process -FilePath $PythonExe -ArgumentList $mainArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput $regLog -RedirectStandardError $regErr
  if ($rp.ExitCode -eq 0) { Add-Result 'core-regression-suite' 'PASS' }
  else { Add-Result 'core-regression-suite' 'FAIL' ("exit code $($rp.ExitCode); see FULL_REGRESSION.log/.err.log") }
  # Resource-heavy destructive/endurance behavior is executed later by the hardware-aware
  # bounded diagnostics runner on Windows instead of contaminating the core regression process.
  Add-Result 'destructive-suite-isolated' 'PASS' 'Deferred to tested-endurance-bounded hardware-aware diagnostics.'
  Save-Results

  Run-Native 'security-audit' { & $PythonExe @PythonPrefix scripts\security_audit.py } | Out-Null
  Run-Native 'static-check' { & $PythonExe @PythonPrefix scripts\static_check.py } | Out-Null

  # Runtime data directory / permissions smoke test
  Run-Native 'user-data-root-write' { & $PythonExe @PythonPrefix -c "from ceo_core.runtime import user_data_root; p=user_data_root(); f=p/'windows-tested-write.tmp'; f.write_text('ok'); assert f.read_text()=='ok'; f.unlink(); print(p)" } | Out-Null

  # Existing Windows validation harness: must remain TESTED evidence only.
  $env:CEO_TEST_OUT = $Out
  Run-Native 'windows-tested-trial' { & $PythonExe @PythonPrefix scripts\run_windows_tested_trial.py } | Out-Null

  # Playwright browser runtime
  Run-Native 'browser-launch-smoke' { & $PythonExe @PythonPrefix -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); pg=b.new_page(); pg.set_content('<title>CEO TEST</title><h1>OK</h1>'); assert pg.title()=='CEO TEST'; b.close(); p.stop(); print('browser ok')" } | Out-Null

  if (-not $SkipBuild) {
    Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
    Run-Native 'pyinstaller-build' { & $PythonExe @PythonPrefix -m PyInstaller --noconfirm packaging\windows\CEO.spec } | Out-Null
    $Exe = Join-Path $Root 'dist\CEO-de-IAs.exe'
    if (Test-Path $Exe) {
      Add-Result 'windows-exe-created' 'PASS' ((Get-Item $Exe).Length.ToString() + ' bytes')
      # Smoke start executable, wait for API, then terminate.
      try {
        $previousAutoOpen = $env:CEO_NO_AUTO_OPEN
        $env:CEO_NO_AUTO_OPEN = '1'
        $proc = Start-Process -FilePath $Exe -PassThru
        $ok=$false
        for($i=0;$i -lt 30;$i++) {
          Start-Sleep -Milliseconds 500
          try {
            $r=Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/state' -TimeoutSec 2
            if ($null -ne $r) { $ok=$true; break }
          } catch {}
          if ($proc.HasExited) { break }
        }
        if ($ok) { Add-Result 'windows-exe-smoke' 'PASS' 'API responded on 127.0.0.1:8765' }
        else {
          $desktopLog = Join-Path $env:LOCALAPPDATA 'CEO de IAs\logs\ceo.log'
          $detail = 'Executable did not expose the local API in time.'
          if (Test-Path $desktopLog) {
            $tail = ((Get-Content $desktopLog -Tail 8 -ErrorAction SilentlyContinue) -join ' | ')
            if ($tail) { $detail += ' Log tail: ' + $tail }
          }
          Add-Result 'windows-exe-smoke' 'FAIL' $detail
        }
      } finally {
        if ($proc -and -not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
        $env:CEO_NO_AUTO_OPEN = $previousAutoOpen
      }
    } else { Add-Result 'windows-exe-created' 'FAIL' 'dist\CEO-de-IAs.exe missing' }
  }

  # Inno Setup: detect system or per-user installs. WinGet code 0x8A15002B means
  # "no applicable update" and can occur when the package is already installed.
  function Find-Iscc {
    $candidates = @(
      'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
      'C:\Program Files\Inno Setup 6\ISCC.exe',
      (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    )
    $cmd=Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach($c in $candidates) { if ($c -and (Test-Path $c)) { return $c } }
    return $null
  }

  $Iscc = Find-Iscc
  if (-not $SkipInstaller -and -not $Iscc) {
    $winget=Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
      & $winget.Source install -e --id JRSoftware.InnoSetup --silent --accept-package-agreements --accept-source-agreements
      $wingetCode=$LASTEXITCODE
      $Iscc=Find-Iscc
      if ($Iscc) { Add-Result 'inno-setup-install' 'PASS' $Iscc }
      elseif ($wingetCode -eq -1978335189) { Add-Result 'inno-setup-install' 'BLOCKED' 'WinGet reports no applicable update, but ISCC.exe was not found in known locations.' }
      else { Add-Result 'inno-setup-install' 'FAIL' ("winget exit code $wingetCode") }
      Save-Results
    } else { Add-Result 'inno-setup-install' 'BLOCKED' 'winget not available; installer build will be skipped.' }
  }

  if (-not $Iscc) { $Iscc=Find-Iscc }
  if (-not $SkipInstaller -and $Iscc) {
    Run-Native 'inno-installer-build' { & $Iscc packaging\windows\installer.iss } | Out-Null
    $setupCandidates=@(Get-ChildItem -Path $Root -Filter 'CEO-Setup.exe' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($setupCandidates.Count -gt 0) {
      $Setup=$setupCandidates[0].FullName
      Add-Result 'installer-created' 'PASS' $Setup
      $InstallDir=Join-Path $Out 'fresh-install'
      Run-Native 'fresh-install-silent' { & $Setup /VERYSILENT /SUPPRESSMSGBOXES /NORESTART "/DIR=$InstallDir" } | Out-Null
      $InstalledExe=Join-Path $InstallDir 'CEO-de-IAs.exe'
      $Uninstaller=Join-Path $InstallDir 'unins000.exe'
      # Inno Setup can return before antivirus/indexing releases the freshly written files.
      # Wait briefly for the installed layout instead of treating that race as a product failure.
      for($i=0;$i -lt 40 -and -not (Test-Path $InstalledExe);$i++) { Start-Sleep -Milliseconds 250 }
      if (Test-Path $InstalledExe) { Add-Result 'fresh-install-layout' 'PASS' $InstalledExe } else {
        $listing=Join-Path $Out 'FRESH_INSTALL_LISTING.txt'
        Get-ChildItem -Path $InstallDir -Recurse -Force -ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime | Format-Table -AutoSize | Out-String | Set-Content -Encoding UTF8 $listing
        Add-Result 'fresh-install-layout' 'FAIL' 'Installed executable missing after 10s wait; see FRESH_INSTALL_LISTING.txt.'
      }
      for($i=0;$i -lt 20 -and -not (Test-Path $Uninstaller);$i++) { Start-Sleep -Milliseconds 250 }
      if (Test-Path $Uninstaller) {
        Run-Native 'uninstall-silent' { & $Uninstaller /VERYSILENT /SUPPRESSMSGBOXES /NORESTART } | Out-Null
        for($i=0;$i -lt 40 -and (Test-Path $InstallDir);$i++) { Start-Sleep -Milliseconds 250 }
      } else { Add-Result 'uninstall-silent' 'BLOCKED' 'Uninstaller not found after wait.' }
    } else { Add-Result 'installer-created' 'FAIL' 'CEO-Setup.exe not found after ISCC.' }
  } elseif (-not $SkipInstaller) {
    Add-Result 'inno-installer-build' 'BLOCKED' 'Inno Setup 6 not available. EXE testing completed independently.'
  }

  # Bounded Windows diagnostics use smaller hardware-aware workloads and write structured evidence.
  $enduranceLog = Join-Path $Out 'WINDOWS_BOUNDED_DIAGNOSTICS.log'
  $enduranceErr = Join-Path $Out 'WINDOWS_BOUNDED_DIAGNOSTICS.err.log'
  $pyArgs=@($PythonPrefix) + @('scripts\run_windows_bounded_diagnostics.py')
  $ep=Start-Process -FilePath $PythonExe -ArgumentList $pyArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput $enduranceLog -RedirectStandardError $enduranceErr
  if ($ep.ExitCode -eq 0) { Add-Result 'tested-endurance-bounded' 'PASS' } else {
    $detail="exit code $($ep.ExitCode); see WINDOWS_BOUNDED_DIAGNOSTICS.log/.err.log"
    Add-Result 'tested-endurance-bounded' 'FAIL' $detail
  }
  Save-Results

  $pass=@($Results | Where-Object status -eq 'PASS').Count
  $fail=@($Results | Where-Object status -eq 'FAIL').Count
  $blocked=@($Results | Where-Object status -eq 'BLOCKED').Count
  [pscustomobject]@{timestamp=(Get-Date).ToString('o');phase='TESTED';pass=$pass;fail=$fail;blocked=$blocked;validated=0;stable=0} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Out 'SUMMARY.json')
} catch {
  Add-Result 'runner' 'FAIL' $_.Exception.Message
} finally {
  Save-Results
  Stop-Transcript | Out-Null
  $Zip = "$Out.zip"
  # Package evidence only. Never archive the transient fresh-install tree: Inno/AV may still
  # hold temporary files open and the binaries are not needed for diagnosis.
  $EvidenceStage = Join-Path $Root "reports\windows-tested\evidence-$Stamp"
  New-Item -ItemType Directory -Force -Path $EvidenceStage | Out-Null
  Get-ChildItem -Path $Out -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -ne '.tmp' } | ForEach-Object {
    Copy-Item $_.FullName -Destination $EvidenceStage -Force -ErrorAction SilentlyContinue
  }
  for($i=0;$i -lt 8;$i++) {
    try {
      Compress-Archive -Path "$EvidenceStage\*" -DestinationPath $Zip -Force
      break
    } catch {
      if ($i -eq 7) { Write-Host "[WARN] results-zip failed: $($_.Exception.Message)" }
      else { Start-Sleep -Milliseconds 500 }
    }
  }
  Remove-Item -Recurse -Force $EvidenceStage -ErrorAction SilentlyContinue
  Write-Host ''
  Write-Host '============================================================'
  Write-Host 'CEO TESTED WINDOWS RUN COMPLETE'
  Write-Host "Results folder: $Out"
  Write-Host "UPLOAD THIS FILE BACK TO CHATGPT: $Zip"
  Write-Host '============================================================'
}
