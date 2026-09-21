from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from .in_app_updater import InAppUpdater


def _json(path: Path, payload: dict[str, Any]) -> None:
    InAppUpdater._atomic_json(path, payload)


def _fixture(version: str):
    td = tempfile.TemporaryDirectory(prefix="ceo-atomic-cutover-")
    root = Path(td.name)
    updater = InAppUpdater(root / "data", trusted_keys={})
    old = root / "stable"
    old.mkdir()
    (old / "ABRIR_CEO.cmd").write_text("@echo off\n", encoding="utf-8")
    _json(updater.current_path, {"version": "stable", "root": str(old), "launcher": "ABRIR_CEO.cmd", "status": "healthy"})
    cand = updater.versions / updater._safe_version(version)
    cand.mkdir(parents=True)
    launch = cand / "ABRIR_CEO.cmd"
    launch.write_text("@echo off\n", encoding="utf-8")
    _json(cand / updater.RECEIPT_NAME, {
        "version": version,
        "launcher": "ABRIR_CEO.cmd",
        "manifest_version": 1,
        "staged_file_hashes": {"ABRIR_CEO.cmd": hashlib.sha256(launch.read_bytes()).hexdigest()},
    })
    return td, updater, old


def run_atomic_cutover_drill_v1(*, version: str) -> dict[str, Any]:
    td, updater, old = _fixture(version)
    try:
        first = updater.activate(version)
        duplicate_blocked = False
        duplicate_error = ""
        try:
            updater.activate(version)
        except Exception as exc:
            duplicate_blocked = True
            duplicate_error = f"{type(exc).__name__}: {exc}"
        previous = updater.previous_pointer() or {}
        rollback = updater.rollback(reason="drill", failed_version=version)
        restored = rollback.get("pointer") or {}
        return {
            "ok": bool(
                first.get("activation_id") and duplicate_blocked and
                previous.get("version") == "stable" and
                restored.get("version") == "stable" and Path(str(restored.get("root"))) == old
            ),
            "duplicate_activation_blocked": duplicate_blocked,
            "duplicate_error": duplicate_error,
            "previous_version_after_first_cutover": previous.get("version"),
            "rollback_restored_version": restored.get("version"),
            "activation_id": first.get("activation_id"),
        }
    finally:
        td.cleanup()
