from __future__ import annotations

import asyncio
import importlib.util
import os
import pathlib
import sys
import tempfile
import threading

ROOT = pathlib.Path(os.environ["CEO_DEV312_BUILD_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location(
    "dev312_work_mode", ROOT / "scripts" / "ceo_stdlib_work_mode.py"
)
work = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(work)
CEOEngine = work.CEOEngine


def make_engine(transport_cls):
    e = object.__new__(CEOEngine)
    e.GeminiInteractionsTransport = transport_cls
    e._provider_validation_epoch = 0
    e._provider_validation_source = "none"
    e._provider_validation_lock = threading.Lock()
    e._pending_gemini_key = None
    e.provider_validation_in_progress = False
    e._provider_revalidation_interval_seconds = 300.0
    e._next_provider_revalidation_ts = 0.0
    e.gemini_key = None
    e.gemini_validation_error = None
    e.gemini_key_recognized = False
    e.gemini_key_status = None
    e.execution_enabled = False
    e.gemini_model = None
    e.provider_mode = "plan-only (sin Gemini)"
    e.scheduler = None
    e.state = None
    e.router = None

    async def snap():
        return {
            "execution_enabled": e.execution_enabled,
            "gemini_key_recognized": e.gemini_key_recognized,
            "gemini_key_status": e.gemini_key_status,
            "provider_mode": e.provider_mode,
            "gemini_model": e.gemini_model,
        }

    e.snapshot = snap
    return e


class ImmediateTransport:
    response = {}
    def __init__(self, *, api_key=None, model=None, **kwargs):
        self.api_key = api_key
    async def probe_live(self):
        return dict(self.response)


def test_dpapi_trust_roundtrip():
    if sys.platform != "win32":
        print("SKIP_DPAPI_NON_WINDOWS")
        return {"skipped": True}

    key = "AIza" + "A"*35
    other = "AIza" + "B"*35
    with tempfile.TemporaryDirectory(prefix="dev312-localapp-") as td:
        old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = td
        try:
            assert work._save_windows_dpapi_gemini_key(key) is True
            assert work._save_windows_dpapi_gemini_trust(
                key, model="gemini-test", source="qualification"
            ) is True
            loaded_key = work._load_windows_dpapi_gemini_key()
            trust = work._load_windows_dpapi_gemini_trust(key)
            wrong = work._load_windows_dpapi_gemini_trust(other)
            assert loaded_key == key
            assert trust.get("fingerprint") == work._gemini_key_fingerprint(key)
            assert trust.get("model") == "gemini-test"
            assert wrong == {}
            raw = work._gemini_trust_path().read_bytes()
            assert key.encode() not in raw
            assert work._gemini_key_fingerprint(key).encode() not in raw
            return {
                "key_roundtrip": True,
                "trust_roundtrip": True,
                "wrong_key_rejected": True,
                "trust_file_encrypted": True,
            }
        finally:
            if old is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old


async def test_prior_trust_survives_connect_error():
    key = "AIza" + "C"*35
    ImmediateTransport.response = {
        "ok": False,
        "status": "ERROR",
        "detail": "ConnectError: synthetic offline",
        "authenticated": None,
        "models_visible": 0,
    }
    e = make_engine(ImmediateTransport)

    old_load = work._load_windows_dpapi_gemini_trust
    old_save_key = work._save_windows_dpapi_gemini_key
    old_save_trust = work._save_windows_dpapi_gemini_trust
    try:
        work._load_windows_dpapi_gemini_trust = lambda candidate: (
            {"fingerprint": "trusted", "model": "gemini-prev"} if candidate == key else {}
        )
        work._save_windows_dpapi_gemini_key = lambda candidate: True
        work._save_windows_dpapi_gemini_trust = lambda *a, **k: True

        out = await e.activate_gemini(key)
        assert e.gemini_key == key
        assert e.gemini_key_recognized is True
        assert e.execution_enabled is False
        assert e.provider_mode == "gemini-authenticated-waiting"
        assert e.gemini_key_status == "ERROR"
        assert out["gemini_key_recognized"] is True
        return {
            "recognized": e.gemini_key_recognized,
            "execution_enabled": e.execution_enabled,
            "provider_mode": e.provider_mode,
            "status": e.gemini_key_status,
        }
    finally:
        work._load_windows_dpapi_gemini_trust = old_load
        work._save_windows_dpapi_gemini_key = old_save_key
        work._save_windows_dpapi_gemini_trust = old_save_trust


async def test_explicit_401_revokes_trust():
    key = "AIza" + "D"*35
    ImmediateTransport.response = {
        "ok": False,
        "status": 401,
        "detail": "UNAUTHENTICATED",
        "authenticated": False,
        "models_visible": 0,
    }
    e = make_engine(ImmediateTransport)
    e.gemini_key = key
    e.gemini_key_recognized = True
    e.execution_enabled = True
    e.provider_mode = "gemini-live-verified"

    old_load = work._load_windows_dpapi_gemini_trust
    old_forget = work._forget_windows_dpapi_gemini_trust
    calls = {"forgot": 0}
    try:
        work._load_windows_dpapi_gemini_trust = lambda candidate: (
            {"fingerprint": "trusted"} if candidate == key else {}
        )
        work._forget_windows_dpapi_gemini_trust = lambda: calls.__setitem__("forgot", calls["forgot"] + 1) or True
        failed = False
        try:
            await e.activate_gemini(key)
        except RuntimeError:
            failed = True
        assert failed is True
        assert calls["forgot"] == 1
        assert e.gemini_key is None
        assert e.gemini_key_recognized is False
        assert e.execution_enabled is False
        assert e.provider_mode == "gemini-validation-failed"
        return {"hard_reject": True, "trust_revoked": True}
    finally:
        work._load_windows_dpapi_gemini_trust = old_load
        work._forget_windows_dpapi_gemini_trust = old_forget


def test_startup_and_ui_semantics():
    text = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    assert "startup_trust = _load_windows_dpapi_gemini_trust" in text
    assert '"TRUSTED_PREVIOUSLY_VERIFIED" if startup_trust else None' in text
    assert 'self.provider_mode = "gemini-authenticated-waiting"' in text
    assert 'self.provider_mode = "gemini-validation-deferred"' in text
    assert "Conexión con Gemini temporalmente no disponible." in text
    assert "No se pudo verificar Gemini en este momento. CEO conserva la clave cifrada y reintentará." in text
    return {
        "startup_trust_restore": True,
        "transport_not_auth_failure": True,
        "truthful_ui": True,
    }


def test_dev311_inherited():
    ui = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts" / "launch_current.py").read_text(encoding="utf-8")
    assert "installable=(r&&r.receipt" in ui
    assert "if(phase==='ready_to_install'&&!updateActionBusy)" in ui
    assert "EXISTING_INSTANCE_OPENED" in launcher
    assert "--app={url}" in launcher
    return {"dev311_update_shell": True, "single_instance_app_mode": True}


async def main_async():
    rows = {
        "dpapi": test_dpapi_trust_roundtrip(),
        "transport": await test_prior_trust_survives_connect_error(),
        "hard_reject": await test_explicit_401_revokes_trust(),
        "startup_ui": test_startup_and_ui_semantics(),
        "dev311": test_dev311_inherited(),
    }
    print("DEV312_PROVIDER_TRUST_INTEGRITY_PASS")
    print(rows)


if __name__ == "__main__":
    asyncio.run(main_async())
