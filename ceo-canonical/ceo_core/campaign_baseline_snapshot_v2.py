from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    try:
        row = json.loads(path.read_text(encoding="utf-8-sig"))
        return row if isinstance(row, dict) else {}
    except Exception:
        return {}


def _sha(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return None


class CampaignBaselineSnapshotV2:
    """Read-only, secret-minimal snapshot used before a one-shot physical campaign."""

    def __init__(self, updates_root: str | Path):
        self.root = Path(updates_root)

    def capture(self) -> dict[str, Any]:
        current = _load(self.root / "current.json")
        previous = _load(self.root / "previous.json")
        progress = _load(self.root / "progress.json")
        restart = _load(self.root / "restart-progress.json")
        failure = _load(self.root / "update-failure-latest.json")
        current_root = Path(str(current.get("root") or "")) if current.get("root") else None
        current_launcher = None
        if current_root:
            current_launcher = current_root / str(current.get("launcher") or "ABRIR_CEO.cmd")
        row = {
            "schema_version": 2,
            "captured_at_epoch": time.time(),
            "platform": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "current": {
                "version": current.get("version"),
                "status": current.get("status"),
                "activation_id": current.get("activation_id"),
                "root_exists": bool(current_root and current_root.is_dir()),
                "launcher_exists": bool(current_launcher and current_launcher.is_file()),
                "receipt_sha256": _sha(current_root / ".ceo-update-receipt.json") if current_root else None,
            },
            "previous": {
                "version": previous.get("version"),
                "status": previous.get("status"),
                "root_exists": bool(previous.get("root") and Path(str(previous.get("root"))).is_dir()),
            },
            "update_state": {
                "progress_phase": progress.get("phase"),
                "restart_phase": restart.get("phase"),
                "last_failure_phase": failure.get("phase"),
                "last_failure_outcome": failure.get("outcome"),
            },
            "environment": {
                "localappdata_present": bool(os.getenv("LOCALAPPDATA")),
                "userprofile_present": bool(os.getenv("USERPROFILE")),
            },
        }
        canon = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        row["snapshot_sha256"] = hashlib.sha256(canon).hexdigest()
        row["read_only"] = True
        return row
