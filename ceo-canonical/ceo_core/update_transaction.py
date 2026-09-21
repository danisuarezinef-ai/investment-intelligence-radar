from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


class UpdateTransactionJournal:
    """Small append-only hash-chained update journal.

    It never performs activation or publication. It only records enough evidence
    to diagnose a crash and decide whether recovery is safe/idempotent.
    """

    def __init__(self, updates_root: str | Path):
        self.root = Path(updates_root)
        self.path = self.root / "transaction-journal.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _canonical(row: dict[str, Any]) -> bytes:
        return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _last(self) -> dict[str, Any]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            return json.loads(lines[-1]) if lines else {}
        except Exception:
            return {}

    def append(self, phase: str, *, version: str = "", tx_id: str = "", **fields: Any) -> dict[str, Any]:
        prev = self._last()
        prev_hash = str(prev.get("event_hash") or "")
        body = {
            "schema_version": 1,
            "tx_id": tx_id or str(prev.get("tx_id") or uuid.uuid4().hex),
            "phase": str(phase),
            "version": str(version),
            "epoch": time.time(),
            "prev_hash": prev_hash,
            **fields,
        }
        body["event_hash"] = hashlib.sha256(self._canonical(body)).hexdigest()
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
            f.flush(); os.fsync(f.fileno())
        return body

    def verify(self) -> dict[str, Any]:
        previous = ""
        count = 0
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
            for raw in lines:
                row = json.loads(raw)
                event_hash = str(row.pop("event_hash", ""))
                if str(row.get("prev_hash") or "") != previous:
                    return {"ok": False, "events": count, "reason": "prev_hash_mismatch"}
                actual = hashlib.sha256(self._canonical(row)).hexdigest()
                if actual != event_hash:
                    return {"ok": False, "events": count, "reason": "event_hash_mismatch"}
                previous = event_hash; count += 1
            return {"ok": True, "events": count, "last_hash": previous}
        except Exception as exc:
            return {"ok": False, "events": count, "reason": f"{type(exc).__name__}: {exc}"}

    def recovery_hint(self) -> dict[str, Any]:
        last = self._last()
        phase = str(last.get("phase") or "")
        if not last:
            return {"action": "none", "safe": True}
        if phase in {"healthy", "rolled_back", "preflight_failed", "rejected"}:
            return {"action": "none", "safe": True, "phase": phase}
        if phase in {"download", "verify", "stage", "staged", "preflight", "preflight_ok"}:
            return {"action": "resume_or_discard_candidate", "safe": True, "phase": phase}
        return {"action": "inspect_pointer_then_rollback_if_stale", "safe": False, "phase": phase}
