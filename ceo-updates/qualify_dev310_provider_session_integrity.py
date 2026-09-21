from __future__ import annotations

import asyncio
import importlib.util
import os
import pathlib
import sys
import threading

ROOT = pathlib.Path(os.environ["CEO_DEV310_BUILD_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))

from ceo_core.providers.gemini_interactions import GeminiInteractionsTransport

spec = importlib.util.spec_from_file_location(
    "dev310_work_mode", ROOT / "scripts" / "ceo_stdlib_work_mode.py"
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
    work._save_windows_dpapi_gemini_key = lambda key: True
    return e


class ImmediateTransport:
    responses = {}

    def __init__(self, *, api_key=None, model=None, **kwargs):
        self.api_key = api_key

    async def probe_live(self):
        value = self.responses[self.api_key]
        if isinstance(value, Exception):
            raise value
        return dict(value)


async def test_invalid_candidate_preserves_good_session():
    good = "GOOD_KEY_12345678901234567890"
    bad = "BAD_KEY_123456789012345678901"
    ImmediateTransport.responses = {
        bad: {
            "ok": False,
            "status": 401,
            "authenticated": False,
            "detail": "API key invalid",
            "models_visible": 0,
        }
    }
    e = make_engine(ImmediateTransport)
    e.gemini_key = good
    e.gemini_key_recognized = True
    e.gemini_key_status = "LIVE_VERIFIED"
    e.execution_enabled = True
    e.provider_mode = "gemini-live-verified"
    e.gemini_model = "gemini-test-live"

    failed = False
    try:
        await e.activate_gemini(bad)
    except RuntimeError:
        failed = True
    assert failed
    assert e.gemini_key == good
    assert e.execution_enabled is True
    assert e.gemini_key_recognized is True
    assert e.provider_mode == "gemini-live-verified"
    return {
        "candidate_rejected": failed,
        "good_session_preserved": True,
        "provider_mode": e.provider_mode,
    }


async def test_authenticated_quota_becomes_waiting_not_invalid():
    key = "WAIT_KEY_12345678901234567890"
    ImmediateTransport.responses = {
        key: {
            "ok": False,
            "status": "QUOTA_EXHAUSTED",
            "authenticated": True,
            "detail": "429 resource exhausted",
            "models_visible": 4,
        }
    }
    e = make_engine(ImmediateTransport)
    out = await e.activate_gemini(key)
    assert e.gemini_key == key
    assert e.gemini_key_recognized is True
    assert e.execution_enabled is False
    assert e.provider_mode == "gemini-authenticated-waiting"
    assert e.gemini_key_status == "QUOTA_EXHAUSTED"
    assert out["gemini_key_recognized"] is True
    return {
        "recognized": True,
        "execution_enabled": e.execution_enabled,
        "provider_mode": e.provider_mode,
        "status": e.gemini_key_status,
    }


async def test_last_validation_wins():
    old_key = "OLD_KEY_123456789012345678901"
    new_key = "NEW_KEY_123456789012345678901"
    old_started = asyncio.Event()
    release_old = asyncio.Event()

    class RacingTransport:
        def __init__(self, *, api_key=None, model=None, **kwargs):
            self.api_key = api_key

        async def probe_live(self):
            if self.api_key == old_key:
                old_started.set()
                await release_old.wait()
                return {
                    "ok": False,
                    "status": "QUOTA_EXHAUSTED",
                    "authenticated": True,
                    "detail": "old delayed result",
                    "models_visible": 5,
                }
            return {
                "ok": True,
                "status": 200,
                "authenticated": True,
                "models_visible": 5,
                "model": "gemini-new",
                "verified_generation": True,
            }

    e = make_engine(RacingTransport)
    old_epoch = e._begin_provider_validation("startup")
    old_task = asyncio.create_task(
        e.activate_gemini(
            old_key,
            validation_epoch=old_epoch,
            validation_source="startup",
        )
    )
    await asyncio.wait_for(old_started.wait(), timeout=2)
    latest = await e.activate_gemini(new_key)
    assert latest["execution_enabled"] is True
    release_old.set()
    stale = await asyncio.wait_for(old_task, timeout=2)

    assert e.gemini_key == new_key
    assert e.execution_enabled is True
    assert e.gemini_key_status == "LIVE_VERIFIED"
    assert e.gemini_model == "gemini-new"
    assert stale.get("provider_validation_superseded") is True
    return {
        "latest_key_won": True,
        "stale_result_superseded": True,
        "model": e.gemini_model,
    }


async def test_probe_budget():
    class BudgetProbe(GeminiInteractionsTransport):
        def __init__(self):
            super().__init__(
                api_key="probe-key",
                client=object(),
                max_models=12,
                max_attempts_per_model=3,
            )
            self.calls = []

        async def _candidate_models(self, client):
            return ["m1", "m2", "m3", "m4", "m5"]

        async def _generate(
            self,
            client,
            *,
            model,
            contents,
            max_output_tokens=512,
            attempts=None,
        ):
            self.calls.append((model, attempts))
            raise RuntimeError("synthetic transient failure")

    t = BudgetProbe()
    out = await t.probe_live()
    assert len(t.calls) == 2, t.calls
    assert all(attempts == 1 for _, attempts in t.calls), t.calls
    assert out["ok"] is False
    assert out.get("authenticated") is True
    return {
        "models_attempted": len(t.calls),
        "attempts_per_model": [x[1] for x in t.calls],
        "status": out.get("status"),
    }


def test_ui_truthfulness():
    text = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    assert "Gemini autenticado · EN ESPERA" in text
    assert "CEO reintentará automáticamente; no necesitas crear otra clave" in text
    assert "if(s.execution_enabled)" in text
    assert "Clave autenticada. Proveedor temporalmente en espera; CEO reintentará solo." in text
    assert "provider_validation_superseded" in text
    return {"truthful_waiting_ui": True, "conditional_retry_success": True}


async def main_async():
    rows = {
        "invalid_candidate": await test_invalid_candidate_preserves_good_session(),
        "authenticated_wait": await test_authenticated_quota_becomes_waiting_not_invalid(),
        "last_validation_wins": await test_last_validation_wins(),
        "probe_budget": await test_probe_budget(),
        "ui": test_ui_truthfulness(),
    }
    print("DEV310_PROVIDER_SESSION_INTEGRITY_PASS")
    print(rows)


if __name__ == "__main__":
    asyncio.run(main_async())
