from __future__ import annotations

import hashlib
import json
from typing import Any

ALLOWED_KINDS = {
    "candidate_seen", "preflight_started", "preflight_passed", "preflight_failed",
    "snapshot_recorded", "activation_requested", "activation_observed", "health_passed",
    "health_failed", "rollback_requested", "rollback_observed", "quarantined",
}
FORBIDDEN_AUTHORITY = {"auto_publish", "auto_install", "auto_promote", "spend", "real_trade", "credential_export"}


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(prev: str, seq: int, kind: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canon({"prev": prev, "seq": seq, "kind": kind, "payload": payload})).hexdigest()


class UpdateTransactionLedgerV2:
    def __init__(self, *, max_records: int = 10_000) -> None:
        self.max_records = max(1, min(int(max_records), 100_000))
        self._records: list[dict[str, Any]] = []

    @property
    def records(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._records]

    def append(self, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if len(self._records) >= self.max_records:
            raise OverflowError("ledger_capacity_exceeded")
        kind = str(kind).strip()
        if kind not in ALLOWED_KINDS:
            raise ValueError("ledger_kind_forbidden")
        payload = dict(payload or {})
        authority = {str(v) for v in payload.get("authority", [])} if isinstance(payload.get("authority"), list) else set()
        if authority & FORBIDDEN_AUTHORITY:
            raise PermissionError("forbidden_authority_claim")
        seq = len(self._records) + 1
        prev = self._records[-1]["hash"] if self._records else "0" * 64
        record = {"seq": seq, "kind": kind, "payload": payload, "prev": prev}
        record["hash"] = _digest(prev, seq, kind, payload)
        self._records.append(record)
        return dict(record)

    def verify(self) -> dict[str, Any]:
        prev = "0" * 64
        problems: list[str] = []
        for expected_seq, record in enumerate(self._records, 1):
            if record.get("seq") != expected_seq:
                problems.append(f"seq:{expected_seq}")
            if record.get("prev") != prev:
                problems.append(f"prev:{expected_seq}")
            expected = _digest(prev, expected_seq, str(record.get("kind") or ""), dict(record.get("payload") or {}))
            if record.get("hash") != expected:
                problems.append(f"hash:{expected_seq}")
            prev = str(record.get("hash") or "")
        return {
            "schema_version": 2,
            "ok": not problems,
            "records": len(self._records),
            "head_sha256": prev if self._records else "0" * 64,
            "problems": problems,
            "side_effects_executed": False,
        }
