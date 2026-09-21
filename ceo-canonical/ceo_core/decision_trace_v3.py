from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from .models import ProjectState, Task


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            low = str(k).lower()
            if any(token in low for token in ("password", "secret", "token", "api_key", "apikey", "cookie", "authorization", "credential")):
                out[str(k)] = "[REDACTED]"
            else:
                out[str(k)] = _safe(v)
        return out
    if isinstance(value, list):
        return [_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class DecisionTraceV3:
    """Bounded hash-chained explanation trail for scheduler choices.

    This complements the evidence ledger: it explains *why* a task/provider was
    chosen or blocked without storing credentials or private signing material.
    """

    KEY = "decision_trace_v3"
    MAX = 5000

    def append(self, state: ProjectState, event: str, *, task: Task | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
        root = state.metadata.setdefault(self.KEY, {"entries": [], "last_hash": ""})
        entries = root.setdefault("entries", [])
        prev = str(root.get("last_hash") or "")
        payload = {
            "seq": int(entries[-1]["seq"] + 1) if entries else 1,
            "ts": _now(),
            "event": str(event),
            "task_id": task.id if task else None,
            "task_title": task.title if task else None,
            "data": _safe(data or {}),
            "prev_hash": prev,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        payload["entry_hash"] = sha256(raw).hexdigest()
        entries.append(payload)
        if len(entries) > self.MAX:
            # Keep a verifiable bounded suffix. The first retained row becomes a
            # checkpoint root rather than pretending its predecessor is available.
            entries[:] = entries[-self.MAX:]
            entries[0]["checkpoint_root"] = True
        root["last_hash"] = entries[-1]["entry_hash"]
        root["count"] = int(root.get("count", 0) or 0) + 1
        root["updated_at"] = payload["ts"]
        return payload

    def verify(self, state: ProjectState) -> dict[str, Any]:
        root = state.metadata.get(self.KEY, {}) or {}
        entries = list(root.get("entries", []) or [])
        previous = None
        for idx, row in enumerate(entries):
            if idx == 0 and row.get("checkpoint_root"):
                previous = str(row.get("prev_hash") or "")
            elif idx == 0:
                previous = ""
            expected_prev = previous
            if str(row.get("prev_hash") or "") != expected_prev:
                return {"valid": False, "entries": len(entries), "bad_index": idx, "reason": "prev_hash_mismatch"}
            body = {k: row[k] for k in ("seq", "ts", "event", "task_id", "task_title", "data", "prev_hash")}
            raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            digest = sha256(raw).hexdigest()
            if digest != row.get("entry_hash"):
                return {"valid": False, "entries": len(entries), "bad_index": idx, "reason": "entry_hash_mismatch"}
            previous = digest
        if entries and str(root.get("last_hash") or "") != str(entries[-1].get("entry_hash") or ""):
            return {"valid": False, "entries": len(entries), "bad_index": len(entries)-1, "reason": "tail_hash_mismatch"}
        return {"valid": True, "entries": len(entries), "last_hash": str(root.get("last_hash") or "")}
