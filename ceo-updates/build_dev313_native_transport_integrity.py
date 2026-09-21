from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.88-rc1-provider-trust-integrity.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV313_BUILD_ROOT", "/tmp/ceo-dev313-native-transport"))
OLD_VERSION = "1.5.88-rc1-provider-trust-integrity"
VERSION = "1.5.89-rc1-native-transport-integrity"


def patch_transport() -> None:
    p = ROOT / "ceo_core" / "providers" / "gemini_interactions.py"
    s = p.read_text(encoding="utf-8")

    imports_old = """import asyncio
import json
import os
import time
import uuid
from typing import Any, Awaitable, Callable
"""
    imports_new = """import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import uuid
from typing import Any, Awaitable, Callable
"""
    if s.count(imports_old) != 1:
        raise RuntimeError(f"transport imports anchor={s.count(imports_old)}")
    s = s.replace(imports_old, imports_new, 1)

    helper_anchor = """    async def _request_json(
        self,
        client: httpx.AsyncClient,
"""
    helper_block = r'''    def _make_client(self, timeout_seconds: float) -> httpx.AsyncClient:
        """Prefer IPv4 on Windows; the host may resolve IPv6 first even when only IPv4 is routable."""
        if sys.platform == "win32":
            try:
                transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=0)
                return httpx.AsyncClient(timeout=float(timeout_seconds), transport=transport, trust_env=False)
            except Exception:
                pass
        return httpx.AsyncClient(timeout=float(timeout_seconds), trust_env=False)

    async def _windows_native_request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[httpx.Response, dict[str, Any]]:
        """Windows-native HTTPS fallback.

        The request is executed by PowerShell/WinHTTP after Python/httpx network
        failure. Sensitive headers and JSON body are supplied through stdin, not
        the command line, so the Gemini key is not exposed in process arguments.
        """
        if sys.platform != "win32":
            raise RuntimeError("native Windows transport unavailable on this platform")
        ps = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("powershell")
        if not ps:
            raise RuntimeError("PowerShell transport unavailable")

        full_url = str(url)
        if params:
            query = urllib.parse.urlencode(
                [(str(k), str(v)) for k, v in params.items() if v is not None],
                doseq=True,
            )
            if query:
                full_url += ("&" if "?" in full_url else "?") + query

        envelope = {
            "method": str(method or "GET").upper(),
            "url": full_url,
            "headers": dict(headers or {}),
            "payload": payload,
            "timeout": max(3, int(timeout_seconds or min(self.timeout_seconds, 30.0))),
        }
        ps_script = r"""
$ErrorActionPreference='Stop'
$raw=[Console]::In.ReadToEnd()
$req=$raw | ConvertFrom-Json
$headers=@{}
if($req.headers){
  foreach($p in $req.headers.PSObject.Properties){$headers[$p.Name]=[string]$p.Value}
}
$invoke=@{
  UseBasicParsing=$true
  Uri=[string]$req.url
  Method=[string]$req.method
  Headers=$headers
  TimeoutSec=[int]$req.timeout
}
if($null -ne $req.payload){
  $invoke['ContentType']='application/json'
  $invoke['Body']=($req.payload | ConvertTo-Json -Depth 40 -Compress)
}
try{
  $resp=Invoke-WebRequest @invoke
  $out=[ordered]@{
    transport_ok=$true
    status=[int]$resp.StatusCode
    body=[string]$resp.Content
    content_type=[string]$resp.Headers['Content-Type']
  }
}catch{
  $status=$null
  try{$status=[int]$_.Exception.Response.StatusCode.value__}catch{}
  if($null -eq $status){try{$status=[int]$_.Exception.Response.StatusCode}catch{}}
  if($null -eq $status){
    $out=[ordered]@{transport_ok=$false;error=[string]$_.Exception.Message}
  }else{
    $body=''
    if($_.ErrorDetails -and $_.ErrorDetails.Message){$body=[string]$_.ErrorDetails.Message}
    $out=[ordered]@{transport_ok=$true;status=$status;body=$body;content_type='application/json'}
  }
}
[Console]::Out.Write(($out | ConvertTo-Json -Depth 8 -Compress))
"""
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = await asyncio.create_subprocess_exec(
            ps,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=creationflags,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(json.dumps(envelope, ensure_ascii=False).encode("utf-8")),
            timeout=max(8.0, float(envelope["timeout"]) + 8.0),
        )
        if proc.returncode != 0:
            detail = stderr.decode("utf-8", "replace")[-500:]
            raise RuntimeError(f"Windows native Gemini transport failed: {detail}")
        try:
            row = json.loads(stdout.decode("utf-8", "replace"))
        except Exception as exc:
            raise RuntimeError("Windows native Gemini transport returned invalid JSON") from exc
        if not isinstance(row, dict) or not row.get("transport_ok"):
            raise RuntimeError(
                "Windows native Gemini transport unavailable: "
                + self._redact(str((row or {}).get("error") if isinstance(row, dict) else row))[:500]
            )

        status = int(row.get("status") or 0)
        body = str(row.get("body") or "")
        request = httpx.Request(str(method).upper(), full_url)
        response = httpx.Response(
            status,
            headers={"Content-Type": str(row.get("content_type") or "application/json")},
            text=body,
            request=request,
        )
        response.raise_for_status()
        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError("Gemini native transport returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("Gemini native transport returned non-object JSON")
        return response, data

    async def _request_json(
        self,
        client: httpx.AsyncClient,
'''
    if s.count(helper_anchor) != 1:
        raise RuntimeError(f"transport helper anchor={s.count(helper_anchor)}")
    s = s.replace(helper_anchor, helper_block, 1)

    except_old = """            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError, httpx.ReadError) as exc:
                last_exc = exc
                if attempt < max_attempts:
                    await self._bounded_sleep(attempt, response)
                    continue
                raise RuntimeError(f"Gemini temporalmente inaccesible: {type(exc).__name__}") from exc
"""
    except_new = """            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError, httpx.ReadError) as exc:
                last_exc = exc
                if attempt < max_attempts:
                    await self._bounded_sleep(attempt, response)
                    continue
                # Production Windows fallback: the host diagnostics may prove
                # WinHTTP/curl connectivity even when Python/httpx cannot connect.
                if sys.platform == "win32" and self._client is None:
                    try:
                        native_response, native_data = await self._windows_native_request_json(
                            method,
                            url,
                            headers=headers,
                            params=params,
                            payload=payload,
                            timeout_seconds=min(self.timeout_seconds, 30.0),
                        )
                        self._last_probe = dict(self._last_probe or {})
                        self._last_probe["network_transport"] = "windows-native"
                        self._last_probe["httpx_error"] = type(exc).__name__
                        return native_response, native_data
                    except httpx.HTTPStatusError:
                        raise
                    except Exception as native_exc:
                        raise RuntimeError(
                            "Gemini inaccesible por httpx y transporte nativo: "
                            f"{type(exc).__name__} / {type(native_exc).__name__}: "
                            f"{self._redact(native_exc)}"
                        ) from native_exc
                raise RuntimeError(f"Gemini temporalmente inaccesible: {type(exc).__name__}") from exc
"""
    if s.count(except_old) != 1:
        raise RuntimeError(f"network fallback anchor={s.count(except_old)}")
    s = s.replace(except_old, except_new, 1)

    client_old_1 = "client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)"
    client_new_1 = "client = self._client or self._make_client(self.timeout_seconds)"
    if s.count(client_old_1) != 1:
        raise RuntimeError(f"send client anchor={s.count(client_old_1)}")
    s = s.replace(client_old_1, client_new_1, 1)

    client_old_2 = "client = self._client or httpx.AsyncClient(timeout=min(self.timeout_seconds, 30.0))"
    client_new_2 = "client = self._client or self._make_client(min(self.timeout_seconds, 30.0))"
    if s.count(client_old_2) != 1:
        raise RuntimeError(f"probe client anchor={s.count(client_old_2)}")
    s = s.replace(client_old_2, client_new_2, 1)

    # Report which network route actually succeeded.
    success_anchor = '''                        "authenticated": True,
                        "verified_at_monotonic": now,
'''
    success_new = '''                        "authenticated": True,
                        "network_transport": (self._last_probe or {}).get("network_transport", "httpx-ipv4" if sys.platform == "win32" and self._client is None else "httpx"),
                        "verified_at_monotonic": now,
'''
    if s.count(success_anchor) != 1:
        raise RuntimeError(f"probe transport metadata anchor={s.count(success_anchor)}")
    s = s.replace(success_anchor, success_new, 1)

    p.write_text(s, encoding="utf-8")


def patch_work_mode() -> None:
    p = ROOT / "scripts" / "ceo_stdlib_work_mode.py"
    s = p.read_text(encoding="utf-8")

    # Backend must also allow project intake while the external provider is down.
    # Local planning/scheduler state can exist; only IA-dependent leaves wait.
    backend_old = '''    async def start_project(self, body: dict[str, Any]):
        if not self.execution_enabled:
            raise RuntimeError("Gemini no está validado. Actívalo primero; no se creará un proyecto que parezca estar trabajando cuando está pausado.")
        goal_text = str(body.get("goal") or "").strip()
'''
    backend_new = '''    async def start_project(self, body: dict[str, Any]):
        goal_text = str(body.get("goal") or "").strip()
'''
    if s.count(backend_old) != 1:
        raise RuntimeError(f"provider-independent backend anchor={s.count(backend_old)}")
    s = s.replace(backend_old, backend_new, 1)

    # Don't make the entire local CEO UI unusable because a provider is waiting.
    ui_old = """$('power').value=s.power_percent??30;$('powerLabel').textContent=$('power').value+'%';const hasActive=!!s.active;$('pauseBtn').disabled=!hasActive||!!s.paused;$('resumeBtn').disabled=!hasActive||!s.paused||!live;$('cancelBtn').disabled=!hasActive;$('startBtn').disabled=!live;$('startBtn').title=live?'Iniciar trabajo real':'Primero activa y valida Gemini';
"""
    ui_new = """$('power').value=s.power_percent??30;$('powerLabel').textContent=$('power').value+'%';const hasActive=!!s.active;$('pauseBtn').disabled=!hasActive||!!s.paused;$('resumeBtn').disabled=!hasActive||!s.paused;$('cancelBtn').disabled=!hasActive;$('startBtn').disabled=false;$('startBtn').title=live?'Iniciar trabajo real':(keyRecognized?'Crear proyecto; las tareas IA esperarán al proveedor':'Crear proyecto local; las tareas IA quedarán pendientes hasta configurar proveedor');
"""
    if s.count(ui_old) != 1:
        raise RuntimeError(f"provider-independent UI anchor={s.count(ui_old)}")
    s = s.replace(ui_old, ui_new, 1)

    start_old = """async function startNewProject(){const goal=$('goal').value.trim();const name=$('name').value.trim()||null;const status=$('startStatus');if(!state?.execution_enabled){$('actionBanner').className='banner errb';$('actionBanner').textContent='No iniciado: primero activa y valida Gemini.';if(status)status.textContent='Gemini no está activo.';return}if(goal.length<3){"""
    start_new = """async function startNewProject(){const goal=$('goal').value.trim();const name=$('name').value.trim()||null;const status=$('startStatus');if(goal.length<3){"""
    if s.count(start_old) != 1:
        raise RuntimeError(f"provider-independent start anchor={s.count(start_old)}")
    s = s.replace(start_old, start_new, 1)

    # Expose transport route in snapshot for field diagnosis.
    snap_anchor = '''            "gemini_key_status": self.gemini_key_status,
            "power_percent": state.power_percent,
'''
    snap_new = '''            "gemini_key_status": self.gemini_key_status,
            "gemini_transport": (
                dict(getattr(getattr(self.router, "providers", {}), "get", lambda *_: None)("gemini-interactions").transport.last_probe)
                if False else None
            ),
            "power_percent": state.power_percent,
'''
    # Avoid invasive router assumptions; keep this optional field out if anchor changes.
    if s.count(snap_anchor) != 1:
        raise RuntimeError(f"snapshot anchor={s.count(snap_anchor)}")
    # Do not insert broken runtime introspection; instead add a static diagnostic field.
    snap_new = '''            "gemini_key_status": self.gemini_key_status,
            "gemini_transport_policy": "httpx-ipv4->windows-native",
            "power_percent": state.power_percent,
'''
    s = s.replace(snap_anchor, snap_new, 1)

    p.write_text(s, encoding="utf-8")


def update_contract() -> None:
    for rel in ("scripts/ceo_stdlib_work_mode.py", "scripts/install_windows_bootstrap.py"):
        p = ROOT / rel
        if p.is_file():
            p.write_text(p.read_text(encoding="utf-8").replace(OLD_VERSION, VERSION), encoding="utf-8")

    cpath = ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(cpath.read_text(encoding="utf-8"))
    contract["app_version"] = VERSION
    hashes = dict(contract.get("file_hashes") or {})
    for rel in hashes:
        fp = ROOT / rel
        if not fp.is_file():
            raise RuntimeError(f"missing contract path {rel}")
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    contract["file_hashes"] = hashes
    cpath.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if not BASE.is_file():
        raise RuntimeError(f"missing base {BASE}")
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    patch_transport()
    patch_work_mode()
    update_contract()

    print(json.dumps({
        "ok": True,
        "base": OLD_VERSION,
        "version": VERSION,
        "root": str(ROOT),
        "direct_min_base": "1.5.86-rc1-provider-session-integrity",
        "invariants": [
            "windows_primary_httpx_forces_ipv4",
            "httpx_connect_failure_falls_back_to_windows_native_https",
            "api_key_not_exposed_in_fallback_command_line",
            "provider_outage_does_not_disable_local_project_creation",
            "dev311_and_dev312_fixes_inherited",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
