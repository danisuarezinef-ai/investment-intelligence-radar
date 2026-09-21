from __future__ import annotations

import asyncio
import importlib.util
import os
import pathlib
import sys
import types

import httpx

ROOT = pathlib.Path(os.environ["CEO_DEV313_BUILD_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.providers.gemini_interactions import GeminiInteractionsTransport


async def test_httpx_failure_uses_native_fallback():
    t = GeminiInteractionsTransport(api_key="AIza" + "A"*35, max_attempts_per_model=1)
    calls = {"native": 0}

    class FailingClient:
        async def request(self, method, url, headers=None, params=None, json=None):
            req = httpx.Request(method, url)
            raise httpx.ConnectError("synthetic-connect-failure", request=req)

    async def native(self, method, url, *, headers=None, params=None, payload=None, timeout_seconds=None):
        calls["native"] += 1
        req = httpx.Request(method, url)
        resp = httpx.Response(200, request=req, json={"models": []})
        return resp, {"models": []}

    t._windows_native_request_json = types.MethodType(native, t)
    old_platform = sys.platform
    try:
        sys.platform = "win32"
        resp, data = await t._request_json(
            FailingClient(),
            "GET",
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": t.api_key},
            params={"pageSize": 100},
            attempts=1,
        )
    finally:
        sys.platform = old_platform

    assert resp.status_code == 200
    assert data == {"models": []}
    assert calls["native"] == 1
    assert (t._last_probe or {}).get("network_transport") == "windows-native"
    return {"native_calls": calls["native"], "status": resp.status_code}


def test_source_security_and_ipv4():
    src = (ROOT / "ceo_core" / "providers" / "gemini_interactions.py").read_text(encoding="utf-8")
    assert 'local_address="0.0.0.0"' in src
    assert 'trust_env=False' in src
    assert 'stdin=asyncio.subprocess.PIPE' in src
    assert 'proc.communicate(json.dumps(envelope' in src
    assert '"x-goog-api-key"' not in src[src.index("create_subprocess_exec"):src.index("stdout, stderr", src.index("create_subprocess_exec"))]
    assert 'network_transport" = "windows-native"' not in src  # avoid accidental assignment typo
    return {
        "ipv4_primary": True,
        "native_secret_via_stdin": True,
        "trust_env_disabled": True,
    }


def test_provider_outage_does_not_block_local_project_intake():
    src = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    start = src.index("    async def start_project(self, body: dict[str, Any]):")
    body = src[start:start+5000]
    assert 'Gemini no está validado. Actívalo primero' not in body
    assert 'state.metadata["provider_wait_v1"]' in body
    assert "$('startBtn').disabled=false" in src
    assert "Crear proyecto; las tareas IA esperarán al proveedor" in src
    return {"backend_intake_allowed": True, "ui_intake_allowed": True, "provider_wait_recorded": True}


def test_inherited_dev311_dev312():
    ui = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts" / "launch_current.py").read_text(encoding="utf-8")
    assert "installable=(r&&r.receipt" in ui
    assert "if(phase==='ready_to_install'&&!updateActionBusy)" in ui
    assert "EXISTING_INSTANCE_OPENED" in launcher
    assert "--app={url}" in launcher
    assert "_gemini_trust_path" in ui
    assert "TRUSTED_PREVIOUSLY_VERIFIED" in ui
    return {"dev311_update_shell": True, "dev312_provider_trust": True}


async def test_windows_native_reaches_google_without_real_key():
    if sys.platform != "win32":
        return {"skipped": True}
    t = GeminiInteractionsTransport(api_key="NOT_A_REAL_GEMINI_KEY", max_attempts_per_model=1)
    try:
        await t._windows_native_request_json(
            "GET",
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": "NOT_A_REAL_GEMINI_KEY"},
            params={"pageSize": 1},
            timeout_seconds=15,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        assert status in {400, 401, 403}, status
        return {"reached_google": True, "status": status}
    except Exception as exc:
        raise AssertionError(f"native route did not reach Google: {type(exc).__name__}: {exc}") from exc
    raise AssertionError("fake key unexpectedly succeeded")


async def main_async():
    rows = {
        "fallback": await test_httpx_failure_uses_native_fallback(),
        "security_ipv4": test_source_security_and_ipv4(),
        "local_intake": test_provider_outage_does_not_block_local_project_intake(),
        "inherited": test_inherited_dev311_dev312(),
        "windows_native_live": await test_windows_native_reaches_google_without_real_key(),
    }
    print("DEV313_NATIVE_TRANSPORT_INTEGRITY_PASS")
    print(rows)


if __name__ == "__main__":
    asyncio.run(main_async())
