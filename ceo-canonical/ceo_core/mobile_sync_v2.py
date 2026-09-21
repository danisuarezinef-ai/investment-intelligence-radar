from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any


class MobileSyncV2:
    """Authenticated data-only mobile↔Windows envelope protocol.

    This protocol intentionally carries development/status data, never arbitrary
    commands, publication, installation, spending, credentials or destructive work.
    """

    ALLOWED_KINDS = {"status", "attention", "development_receipt", "test_result", "document_note", "safe_work_item"}

    def __init__(self, key: bytes):
        if not isinstance(key, (bytes, bytearray)) or len(key) < 16:
            raise ValueError("sync key must be at least 16 bytes")
        self.key = bytes(key)
        self._seen: set[str] = set()

    @staticmethod
    def _canon(payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def issue(self, kind: str, payload: dict[str, Any], *, ttl_seconds: int = 600) -> dict[str, Any]:
        if kind not in self.ALLOWED_KINDS:
            raise PermissionError(f"sync kind not allowed: {kind}")
        body = {
            "v": 2, "kind": kind, "payload": payload, "nonce": uuid.uuid4().hex,
            "issued_at": time.time(), "expires_at": time.time() + max(30, min(int(ttl_seconds), 3600)),
            "side_effects_allowed": False,
        }
        sig = hmac.new(self.key, self._canon(body), hashlib.sha256).digest()
        return {**body, "mac": base64.b64encode(sig).decode("ascii")}

    def verify(self, envelope: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
        body = {k: envelope[k] for k in envelope if k != "mac"}
        mac = str(envelope.get("mac") or "")
        expected = base64.b64encode(hmac.new(self.key, self._canon(body), hashlib.sha256).digest()).decode("ascii")
        if not hmac.compare_digest(mac, expected):
            raise PermissionError("invalid mobile sync MAC")
        if str(body.get("kind") or "") not in self.ALLOWED_KINDS:
            raise PermissionError("mobile sync kind not allowed")
        epoch = time.time() if now is None else float(now)
        if epoch > float(body.get("expires_at") or 0):
            raise PermissionError("mobile sync envelope expired")
        nonce = str(body.get("nonce") or "")
        if not nonce or nonce in self._seen:
            raise PermissionError("mobile sync replay rejected")
        self._seen.add(nonce)
        if body.get("side_effects_allowed") is not False:
            raise PermissionError("side effects not permitted")
        return body
