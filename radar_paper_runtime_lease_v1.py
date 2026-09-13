"""Durable singleton lease client for the autonomous PAPER runtime.

The backing Edge Function performs atomic acquire/heartbeat/release against Supabase.
This module has no live-trading or broker authority and fails closed on transport errors.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from radar_supabase_sync import SYNC_TOKEN, SYNC_URL

REAL_TRADING = False
HTTP_TIMEOUT_SECONDS = 35


def _url() -> str:
    explicit = os.environ.get("SUPABASE_PAPER_LEASE_URL", "").strip()
    if explicit:
        return explicit
    base = (SYNC_URL or "").strip()
    if "/radar-sync" in base:
        return base.rsplit("/radar-sync", 1)[0] + "/radar-paper-runtime-lease"
    return ""


def enabled() -> bool:
    return bool(_url() and SYNC_TOKEN)


def _post(action: str, *, owner_id: str = "", session_id: str = "", ttl_seconds: int = 180) -> dict[str, Any]:
    if not enabled():
        out={"ok": False, "status": "NOT_CONFIGURED", "action": action, "lease": None, "real_trading": False}
        print('[paper-runtime-lease] '+json.dumps(out,sort_keys=True),flush=True)
        return out
    body = {"action": action, "owner_id": owner_id, "session_id": session_id, "ttl_seconds": int(ttl_seconds)}
    req = urllib.request.Request(
        _url(), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "X-Radar-Token": SYNC_TOKEN,
                 "User-Agent": "InvestmentIntelligenceRadarPaperLease/1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
            out = json.loads(response.read().decode("utf-8"))
        out["real_trading"] = False
        print('[paper-runtime-lease] '+json.dumps({"action":action,"ok":out.get("ok"),"has_lease":bool(out.get("lease")),"real_trading":False},sort_keys=True),flush=True)
        return out
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
        out={"ok": False, "status": "FAIL_CLOSED", "action": action,
             "error": f"{type(exc).__name__}: {str(exc)[:400]}", "lease": None,
             "real_trading": False}
        print('[paper-runtime-lease] '+json.dumps(out,sort_keys=True),flush=True)
        return out


def acquire(owner_id: str, session_id: str, ttl_seconds: int = 180) -> dict[str, Any]:
    out = _post("acquire", owner_id=owner_id, session_id=session_id, ttl_seconds=ttl_seconds)
    lease = out.get("lease") or {}
    held = out.get("ok") is True and lease.get("owner_id") == owner_id and lease.get("session_id") == session_id
    return {**out, "held": held, "status": "HELD" if held else "BLOCKED", "real_trading": False}


def heartbeat(owner_id: str, session_id: str, ttl_seconds: int = 180) -> dict[str, Any]:
    out = _post("heartbeat", owner_id=owner_id, session_id=session_id, ttl_seconds=ttl_seconds)
    lease = out.get("lease") or {}
    held = out.get("ok") is True and lease.get("owner_id") == owner_id and lease.get("session_id") == session_id
    return {**out, "held": held, "status": "HELD" if held else "LOST", "real_trading": False}


def release(owner_id: str, session_id: str) -> dict[str, Any]:
    out = _post("release", owner_id=owner_id, session_id=session_id)
    return {**out, "real_trading": False}


def status() -> dict[str, Any]:
    out = _post("status")
    lease = out.get("lease") or None
    if lease and lease.get("real_trading") is not False:
        return {"ok": False, "status": "FAIL_CLOSED", "lease": lease,
                "reason": "real_trading_not_false", "real_trading": False}
    return {**out, "status": "OBSERVED" if out.get("ok") else out.get("status", "FAIL_CLOSED"),
            "real_trading": False}


def owner_id() -> str:
    return (os.environ.get("RAILWAY_REPLICA_ID") or os.environ.get("RAILWAY_DEPLOYMENT_ID") or
            os.environ.get("HOSTNAME") or "local-paper-runtime")


def health_snapshot(owner: str, session_id: str) -> dict[str, Any]:
    out = status(); lease = out.get("lease") or {}
    return {
        "status": "HELD" if lease.get("owner_id") == owner and lease.get("session_id") == session_id else "NOT_HELD",
        "owner_id": lease.get("owner_id"), "session_id": lease.get("session_id"),
        "heartbeat_at": lease.get("heartbeat_at"), "expires_at": lease.get("expires_at"),
        "epoch": lease.get("epoch"), "observed_at": datetime.now(timezone.utc).isoformat(),
        "real_trading": False,
    }
