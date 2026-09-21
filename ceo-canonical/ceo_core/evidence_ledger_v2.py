from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, Task


SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "private_key", "authorization", "cookie"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean = {}
        for k, v in value.items():
            if any(marker in str(k).lower() for marker in SENSITIVE_KEYS):
                clean[str(k)] = "<redacted>"
            else:
                clean[str(k)] = _sanitize(v)
        return clean
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, tuple):
        return [_sanitize(v) for v in value]
    return value


class EvidenceLedgerV2:
    """Bounded, tamper-evident execution ledger embedded in ProjectState."""

    VERSION = 2

    def append(self, state: ProjectState, event: str, *, task: Task | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
        ledger = state.metadata.setdefault("evidence_ledger_v2", [])
        prev_hash = str(ledger[-1].get("chain_hash") or "") if ledger else "0" * 64
        payload = {
            "version": self.VERSION,
            "seq": int(ledger[-1].get("seq", 0) or 0) + 1 if ledger else 1,
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": str(event),
            "task_id": task.id if task else None,
            "task_title": task.title if task else None,
            "provider": task.provider_name if task else None,
            "data": _sanitize(data or {}),
            "prev_hash": prev_hash,
        }
        payload_hash = hashlib.sha256(_canonical({k: v for k, v in payload.items() if k != "prev_hash"})).hexdigest()
        chain_hash = hashlib.sha256((prev_hash + payload_hash).encode("ascii")).hexdigest()
        row = {**payload, "payload_hash": payload_hash, "chain_hash": chain_hash}
        ledger.append(row)
        # Keep the detailed state bounded while preserving the previous anchor.
        if len(ledger) > 20_000:
            removed = ledger[:-15_000]
            state.metadata["evidence_ledger_v2_archive_anchor"] = removed[-1]["chain_hash"]
            del ledger[:-15_000]
        state.metadata["evidence_ledger_v2_head"] = {"seq": row["seq"], "chain_hash": chain_hash}
        return row

    def validate(self, state: ProjectState) -> dict[str, Any]:
        ledger = list(state.metadata.get("evidence_ledger_v2", []) or [])
        if not ledger:
            return {"valid": True, "entries": 0, "head": None}
        expected_prev = str(ledger[0].get("prev_hash") or "0" * 64)
        failures = []
        last_seq = 0
        for i, row in enumerate(ledger):
            clean_payload = {k: row.get(k) for k in ("version", "seq", "ts", "event", "task_id", "task_title", "provider", "data")}
            payload_hash = hashlib.sha256(_canonical(clean_payload)).hexdigest()
            chain_hash = hashlib.sha256((expected_prev + payload_hash).encode("ascii")).hexdigest()
            seq = int(row.get("seq", 0) or 0)
            if row.get("prev_hash") != expected_prev or row.get("payload_hash") != payload_hash or row.get("chain_hash") != chain_hash or (last_seq and seq != last_seq + 1):
                failures.append(i)
            expected_prev = str(row.get("chain_hash") or chain_hash)
            last_seq = seq
        return {"valid": not failures, "entries": len(ledger), "head": expected_prev, "failure_indexes": failures[:20]}

    def task_history(self, state: ProjectState, task_id: str) -> list[dict[str, Any]]:
        return [row for row in state.metadata.get("evidence_ledger_v2", []) if row.get("task_id") == task_id]
