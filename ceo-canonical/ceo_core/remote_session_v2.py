from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
import re
import time

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class MutationReceipt:
    accepted: bool
    device_id: str | None
    scope: str
    nonce_hash: str | None
    reason: str
    at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RemoteSessionGuardV2:
    """Adds one-time request nonces and replay rejection to mutating remote scopes."""

    KEY = "remote_session_v2"
    MUTATING = {"project:pause", "project:power", "decision:act"}
    NONCE_RE = re.compile(r"^[A-Za-z0-9_\-]{12,160}$")

    def verify_and_consume(self, protocol, state: ProjectState, token: str, scope: str, nonce: str, *, now: int | None = None) -> MutationReceipt:
        if scope not in self.MUTATING:
            return MutationReceipt(False, None, scope, None, "scope_not_mutating", _now())
        row = protocol.verify_token(state, token, scope, now=now)
        if row is None:
            return MutationReceipt(False, None, scope, None, "invalid_or_expired_token", _now())
        if not self.NONCE_RE.fullmatch(str(nonce or "")):
            return MutationReceipt(False, str(row.get("device_id")), scope, None, "invalid_nonce", _now())
        digest = sha256(f"{row.get('device_id')}|{scope}|{nonce}".encode()).hexdigest()
        root = state.metadata.setdefault(self.KEY, {})
        used = root.setdefault("used_nonce_hashes", {})
        ts = int(time.time() if now is None else now)
        # Keep only one day / 5000 nonces.
        for key, seen in list(used.items()):
            if ts - int(seen or 0) > 86400:
                used.pop(key, None)
        if digest in used:
            receipt = MutationReceipt(False, str(row.get("device_id")), scope, digest, "replay_rejected", _now())
        else:
            used[digest] = ts
            if len(used) > 5000:
                for key, _ in sorted(used.items(), key=lambda kv: kv[1])[:-5000]:
                    used.pop(key, None)
            receipt = MutationReceipt(True, str(row.get("device_id")), scope, digest, "accepted", _now())
        root["last_receipt"] = receipt.to_dict()
        return receipt
