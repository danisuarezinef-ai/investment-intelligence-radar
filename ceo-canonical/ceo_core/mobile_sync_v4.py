from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Iterable

from .mobile_sync_v2 import MobileSyncV2


class MobileSyncV4(MobileSyncV2):
    """Authenticated, resumable, data-only transfer protocol.

    Each chunk is independently MACed by MobileSyncV2 and binds transfer id,
    position, total count and whole-transfer digest. No command authority exists.
    """

    @staticmethod
    def _canon(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def issue_transfer(self, items: Iterable[dict[str, Any]], *, chunk_size: int = 25, ttl_seconds: int = 600) -> list[dict[str, Any]]:
        rows = []
        for row in items:
            kind = str(row.get("kind") or "")
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if kind not in self.ALLOWED_KINDS:
                raise PermissionError(f"sync kind not allowed: {kind}")
            rows.append({"kind": kind, "payload": payload})
        if not rows or len(rows) > 1000:
            raise ValueError("transfer must contain 1..1000 items")
        chunk_size = max(1, min(int(chunk_size), 100))
        transfer_id = uuid.uuid4().hex
        digest = hashlib.sha256(self._canon(rows)).hexdigest()
        total = (len(rows) + chunk_size - 1) // chunk_size
        envelopes = []
        for idx in range(total):
            chunk = rows[idx * chunk_size:(idx + 1) * chunk_size]
            payload = {
                "transfer_id": transfer_id,
                "chunk_index": idx,
                "chunk_count": total,
                "item_count": len(rows),
                "items_sha256": digest,
                "items": chunk,
            }
            envelopes.append(self.issue("safe_work_item", payload, ttl_seconds=ttl_seconds))
        return envelopes

    def verify_transfer(self, envelopes: Iterable[dict[str, Any]], *, now: float | None = None) -> dict[str, Any]:
        bodies = [self.verify(e, now=now) for e in envelopes]
        if not bodies:
            raise PermissionError("empty transfer")
        payloads = [b.get("payload") if isinstance(b.get("payload"), dict) else {} for b in bodies]
        transfer_ids = {str(p.get("transfer_id") or "") for p in payloads}
        counts = {int(p.get("chunk_count") or 0) for p in payloads}
        digests = {str(p.get("items_sha256") or "") for p in payloads}
        item_counts = {int(p.get("item_count") or 0) for p in payloads}
        if len(transfer_ids) != 1 or "" in transfer_ids or len(counts) != 1 or len(digests) != 1 or len(item_counts) != 1:
            raise PermissionError("transfer metadata mismatch")
        chunk_count = next(iter(counts))
        if chunk_count != len(payloads) or chunk_count <= 0:
            raise PermissionError("incomplete transfer")
        by_idx: dict[int, list[dict[str, Any]]] = {}
        for p in payloads:
            idx = int(p.get("chunk_index") or 0)
            if idx in by_idx or idx < 0 or idx >= chunk_count:
                raise PermissionError("duplicate or invalid transfer chunk")
            rows = p.get("items") if isinstance(p.get("items"), list) else []
            by_idx[idx] = rows
        if set(by_idx) != set(range(chunk_count)):
            raise PermissionError("missing transfer chunk")
        rows = [row for idx in range(chunk_count) for row in by_idx[idx]]
        if len(rows) != next(iter(item_counts)):
            raise PermissionError("transfer item count mismatch")
        for row in rows:
            if not isinstance(row, dict) or str(row.get("kind") or "") not in self.ALLOWED_KINDS:
                raise PermissionError("forbidden transfer item")
        actual = hashlib.sha256(self._canon(rows)).hexdigest()
        if actual != next(iter(digests)):
            raise PermissionError("transfer digest mismatch")
        return {
            "transfer_id": next(iter(transfer_ids)),
            "items": rows,
            "items_sha256": actual,
            "chunks_verified": chunk_count,
            "side_effects_allowed": False,
        }
