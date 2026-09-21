from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class MobileJobEnvelope:
    job_id: str
    kind: str
    payload_hash: str
    expires_at: int
    max_seconds: int
    scope: str
    signature: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MobileComputeProtocol:
    """Restricted phone compute jobs. It intentionally has no shell/external-write job type."""

    SAFE_KINDS = {"summarize", "classify", "extract", "rank", "verify_text", "transform_json", "local_benchmark"}

    def __init__(self, secret: bytes):
        if len(secret) < 32:
            raise ValueError("mobile compute secret must be >=32 bytes")
        self.secret = secret

    @staticmethod
    def generate_secret() -> bytes:
        return secrets.token_bytes(32)

    def issue(self, kind: str, payload: Any, *, ttl_seconds: int = 300, max_seconds: int = 120) -> MobileJobEnvelope:
        if kind not in self.SAFE_KINDS:
            raise PermissionError("unsafe or unsupported mobile job kind")
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
        payload_hash = hashlib.sha256(body).hexdigest()
        unsigned = {"job_id": secrets.token_hex(16), "kind": kind, "payload_hash": payload_hash, "expires_at": int(time.time()) + max(15, min(int(ttl_seconds), 1800)), "max_seconds": max(1, min(int(max_seconds), 600)), "scope": "compute:safe"}
        raw = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        sig = hmac.new(self.secret, raw, hashlib.sha256).hexdigest()
        return MobileJobEnvelope(signature=sig, **unsigned)

    def verify(self, envelope: MobileJobEnvelope | dict[str, Any], payload: Any, *, now: int | None = None) -> bool:
        row = envelope.to_dict() if isinstance(envelope, MobileJobEnvelope) else dict(envelope)
        sig = str(row.pop("signature", ""))
        if row.get("kind") not in self.SAFE_KINDS or row.get("scope") != "compute:safe":
            return False
        if int(row.get("expires_at", 0)) < int(time.time() if now is None else now):
            return False
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
        if hashlib.sha256(body).hexdigest() != row.get("payload_hash"):
            return False
        raw = json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
        return hmac.compare_digest(sig, hmac.new(self.secret, raw, hashlib.sha256).hexdigest())
