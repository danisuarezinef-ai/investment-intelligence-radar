from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, asdict
from typing import Any

from .models import ProjectState
from .operator_attention import OperatorAttentionBroker


@dataclass(frozen=True)
class PairingReceipt:
    device_id: str
    paired_at: float
    scopes: tuple[str, ...]
    protocol_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RemoteControlProtocol:
    """Minimal signed protocol for Android/remote operator clients.

    Read-only status is broad; mutations are intentionally restricted to pause/resume,
    power and explicit decision actions.  It does not expose spend, publication,
    destructive actions or arbitrary command execution.
    """

    PROTOCOL_VERSION = 2
    ALLOWED_SCOPES = {"status:read", "attention:read", "project:pause", "project:power", "decision:act"}

    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("remote protocol secret must be at least 32 bytes")
        self.secret = secret
        self.attention = OperatorAttentionBroker()

    @staticmethod
    def generate_secret() -> bytes:
        return secrets.token_bytes(32)

    def pair(self, state: ProjectState, device_id: str, scopes: list[str] | None = None) -> PairingReceipt:
        requested = tuple(sorted(set(scopes or ["status:read", "attention:read", "project:pause", "project:power", "decision:act"])))
        if any(scope not in self.ALLOWED_SCOPES for scope in requested):
            raise PermissionError("unsupported remote scope")
        row = PairingReceipt(str(device_id), time.time(), requested, self.PROTOCOL_VERSION)
        state.metadata.setdefault("paired_remote_devices", {})[row.device_id] = row.to_dict()
        return row

    def issue_token(self, device_id: str, scope: str, *, ttl_seconds: int = 300) -> str:
        if scope not in self.ALLOWED_SCOPES:
            raise PermissionError("unsupported remote scope")
        payload = json.dumps({"device_id": device_id, "scope": scope, "exp": int(time.time()) + max(15, min(ttl_seconds, 3600)), "v": self.PROTOCOL_VERSION}, sort_keys=True, separators=(",", ":")).encode()
        sig = hmac.new(self.secret, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload + sig).decode().rstrip("=")

    def verify_token(self, state: ProjectState, token: str, required_scope: str, *, now: int | None = None) -> dict[str, Any] | None:
        try:
            raw = base64.urlsafe_b64decode(token + "=" * ((4 - len(token) % 4) % 4))
            payload, sig = raw[:-32], raw[-32:]
            if not hmac.compare_digest(sig, hmac.new(self.secret, payload, hashlib.sha256).digest()):
                return None
            row = json.loads(payload.decode())
            if int(row.get("exp", 0)) < int(time.time() if now is None else now):
                return None
            if row.get("scope") != required_scope:
                return None
            paired = (state.metadata.get("paired_remote_devices", {}) or {}).get(str(row.get("device_id")))
            if not paired or required_scope not in set(paired.get("scopes", [])):
                return None
            return row
        except Exception:
            return None

    def status_payload(self, state: ProjectState, observability: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocol_version": self.PROTOCOL_VERSION,
            "project_id": state.id,
            "project_name": state.project_name,
            "goal": state.goal,
            "paused": state.paused,
            "progress": state.progress,
            "power_percent": state.power_percent,
            "observability": observability,
            "attention": self.attention.cards(state),
            "safety": {
                "automatic_spending": False,
                "automatic_publication": False,
                "arbitrary_remote_commands": False,
                "destructive_actions_require_human_gate": True,
            },
        }


def load_or_create_remote_secret(data_root) -> bytes:
    """Load persistent remote-control secret without placing plaintext in project state.

    Windows uses Credential Manager plus a DPAPI-encrypted recovery mirror. Non-Windows
    development/test environments use a mode-0600 local file under user data.
    """
    from pathlib import Path
    import os
    root = Path(data_root) / "remote-control"
    root.mkdir(parents=True, exist_ok=True)
    key_name = "remote-control-hmac-v1"
    if os.name == "nt":
        from .credentials import WindowsCredentialManagerStore, WindowsDPAPIFileSecretStore, MirroredSecretStore
        store = MirroredSecretStore(
            WindowsCredentialManagerStore(namespace="CEO-de-IAs-Remote"),
            WindowsDPAPIFileSecretStore(root / "secrets"),
        )
        encoded = store.get(key_name)
        if encoded:
            raw = base64.urlsafe_b64decode(encoded.encode())
            if len(raw) >= 32:
                return raw
        raw = RemoteControlProtocol.generate_secret()
        store.put(key_name, base64.urlsafe_b64encode(raw).decode())
        return raw
    path = root / ".remote_hmac"
    if path.exists():
        try:
            raw = base64.urlsafe_b64decode(path.read_text(encoding="ascii").strip().encode())
            if len(raw) >= 32:
                return raw
        except Exception:
            pass
    raw = RemoteControlProtocol.generate_secret()
    path.write_text(base64.urlsafe_b64encode(raw).decode(), encoding="ascii")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return raw
