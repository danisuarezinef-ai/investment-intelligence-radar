from __future__ import annotations

import hashlib
import tempfile
import time
from pathlib import Path
from typing import Any

from .in_app_updater import InAppUpdater


def _make_updater(version: str):
    td = tempfile.TemporaryDirectory(prefix="ceo-crash-window-")
    base = Path(td.name)
    u = InAppUpdater(base / "data", trusted_keys={})
    stable = base / "stable"; stable.mkdir(); (stable / "ABRIR_CEO.cmd").write_text("@echo off\n", encoding="utf-8")
    InAppUpdater._atomic_json(u.current_path, {"version":"stable","root":str(stable),"launcher":"ABRIR_CEO.cmd","status":"healthy"})
    cand = u.versions / u._safe_version(version); cand.mkdir(parents=True)
    launch = cand / "ABRIR_CEO.cmd"; launch.write_text("@echo off\n", encoding="utf-8")
    InAppUpdater._atomic_json(cand/u.RECEIPT_NAME, {"version":version,"launcher":"ABRIR_CEO.cmd","manifest_version":1,"staged_file_hashes":{"ABRIR_CEO.cmd":hashlib.sha256(launch.read_bytes()).hexdigest()}})
    return td, u


def run_crash_window_recovery_v1(*, version: str) -> dict[str, Any]:
    # Before pointer swap: recovery must keep stable untouched.
    td1, u1 = _make_updater(version)
    try:
        before = u1.recover_interrupted_update(stale_after_seconds=0)
        before_ok = (u1.current_pointer() or {}).get("version") == "stable" and before.get("rolled_back") is None
    finally:
        td1.cleanup()

    # After pointer swap but before health confirmation: stale recovery must restore stable.
    td2, u2 = _make_updater(version)
    try:
        act = u2.activate(version)
        p = u2.current_pointer() or {}
        p["activated_at_epoch"] = time.time() - 999
        InAppUpdater._atomic_json(u2.current_path, p)
        mid = u2.recover_interrupted_update(stale_after_seconds=1)
        mid_ok = bool(mid.get("rolled_back") and (u2.current_pointer() or {}).get("version") == "stable")
    finally:
        td2.cleanup()

    # After health confirmation: generic recovery must never roll back the healthy candidate.
    td3, u3 = _make_updater(version)
    try:
        act3 = u3.activate(version)
        u3.confirm_health(version, activation_id=act3["activation_id"], health={"ok":True,"version":version,"activation_id":act3["activation_id"]})
        after = u3.recover_interrupted_update(stale_after_seconds=0)
        after_ok = (u3.current_pointer() or {}).get("version") == version and after.get("rolled_back") is None
    finally:
        td3.cleanup()

    return {"ok": bool(before_ok and mid_ok and after_ok), "before_pointer_swap": before_ok,
            "pending_health_recovered": mid_ok, "healthy_candidate_preserved": after_ok}
