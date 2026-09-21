from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Iterable

from .mobile_sync_v2 import MobileSyncV2


class MobileSyncV3(MobileSyncV2):
    """Data-only sync v3 with ordered batches and transcript continuity."""

    def __init__(self, key: bytes):
        super().__init__(key)
        self._last_sequence = 0
        self._transcript = "0" * 64

    @staticmethod
    def _digest(value: Any) -> str:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def issue_batch(self, items: Iterable[dict[str, Any]], *, ttl_seconds: int = 600) -> dict[str, Any]:
        rows = []
        for item in items:
            kind = str(item.get("kind") or "")
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            if kind not in self.ALLOWED_KINDS:
                raise PermissionError(f"sync kind not allowed: {kind}")
            rows.append({"kind": kind, "payload": payload})
        if not rows or len(rows) > 100:
            raise ValueError("batch must contain 1..100 data-only items")
        seq = self._last_sequence + 1
        payload = {"sequence": seq, "previous_transcript": self._transcript, "items": rows}
        envelope = self.issue("safe_work_item", payload, ttl_seconds=ttl_seconds)
        digest = self._digest({k: v for k, v in envelope.items() if k != "mac"})
        self._last_sequence = seq
        self._transcript = hashlib.sha256((self._transcript + digest).encode("ascii")).hexdigest()
        envelope["batch_transcript"] = self._transcript
        return envelope

    def verify_batch(self, envelope: dict[str, Any], *, expected_sequence: int, expected_previous_transcript: str, now: float | None = None) -> dict[str, Any]:
        # batch_transcript is transport metadata and is not covered by v2 MAC.
        signed = {k: v for k, v in envelope.items() if k != "batch_transcript"}
        body = self.verify(signed, now=now)
        payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
        if int(payload.get("sequence") or 0) != int(expected_sequence):
            raise PermissionError("mobile sync sequence mismatch")
        if str(payload.get("previous_transcript") or "") != str(expected_previous_transcript):
            raise PermissionError("mobile sync transcript mismatch")
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        if not items or len(items) > 100:
            raise PermissionError("invalid mobile sync batch")
        for row in items:
            if not isinstance(row, dict) or str(row.get("kind") or "") not in self.ALLOWED_KINDS:
                raise PermissionError("forbidden item in mobile sync batch")
        return {"body": body, "items": items, "side_effects_allowed": False}
