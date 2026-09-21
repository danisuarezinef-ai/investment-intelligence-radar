from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class MobileDevelopmentQueue:
    """Side-effect-free queue for work prepared from the mobile workflow."""

    ALLOWED_KINDS = {
        "analyze", "design", "test_plan", "static_test", "simulate", "benchmark_local",
        "document", "review", "compare_candidate", "prepare_patch",
    }
    FORBIDDEN_CAPABILITIES = {
        "spend", "payment", "purchase", "publish", "remote_write", "install", "activate",
        "delete", "destructive", "credential_change", "account_change", "real_trade", "shell_arbitrary",
    }

    def __init__(self, root: str | Path):
        self.path = Path(root) / "mobile-development-queue.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict[str, Any]]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    def enqueue(self, *, kind: str, title: str, payload: dict[str, Any] | None = None, capabilities: list[str] | None = None) -> dict[str, Any]:
        kind = str(kind)
        caps = {str(x) for x in (capabilities or [])}
        if kind not in self.ALLOWED_KINDS:
            raise ValueError(f"mobile development kind not allowed: {kind}")
        blocked = sorted(caps & self.FORBIDDEN_CAPABILITIES)
        if blocked:
            raise PermissionError(f"mobile queue forbids capabilities: {', '.join(blocked)}")
        row = {
            "id": uuid.uuid4().hex,
            "kind": kind,
            "title": str(title)[:300],
            "payload": payload or {},
            "capabilities": sorted(caps),
            "status": "queued",
            "created_at_epoch": time.time(),
            "external_side_effects_allowed": False,
        }
        rows = self._load(); rows.append(row); rows = rows[-1000:]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        return row

    def snapshot(self) -> dict[str, Any]:
        rows = self._load()
        return {
            "queued": sum(1 for r in rows if r.get("status") == "queued"),
            "items": rows[-100:],
            "external_side_effects_allowed": False,
        }
