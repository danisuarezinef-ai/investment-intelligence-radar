from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .credentials import (MemorySecretStore, MirroredSecretStore, SecretStore, WindowsCredentialManagerStore, WindowsDPAPIFileSecretStore)


PRIVATE_KEY_NAME = "release_signing_ed25519_private_v1"
PUBLIC_KEY_NAME = "release_signing_ed25519_public_v1"
KEY_ID_NAME = "release_signing_key_id_v1"
CREATED_AT_NAME = "release_signing_created_at_v1"
CREDENTIAL_NAMESPACE = "CEO-de-IAs-Release"
KEY_ID_PREFIX = "ceo-user"


@dataclass(slots=True)
class ReleaseSignerStatus:
    configured: bool
    key_id: str = ""
    public_key_b64: str = ""
    public_fingerprint: str = ""
    created_at: str = ""
    storage: str = ""
    self_test: bool = False


class ReleaseSigningAuthority:
    """Persistent release signer whose private key never belongs to the source tree.

    On Windows the default backend is Credential Manager. Tests can inject any
    SecretStore (normally MemorySecretStore). Only the public key and metadata may
    be exported to disk for diagnostics; the raw private key remains in the store.
    """

    def __init__(self, store: SecretStore | None = None) -> None:
        if store is None:
            if os.name != "nt":
                raise RuntimeError("Persistent release signing authority requires Windows")
            from .runtime import user_data_root
            primary = WindowsCredentialManagerStore(namespace=CREDENTIAL_NAMESPACE)
            backup = WindowsDPAPIFileSecretStore(user_data_root() / "updates" / "release-signer-vault")
            store = MirroredSecretStore(primary, backup)
        self.store = store

    @staticmethod
    def _public_raw(key: Ed25519PrivateKey) -> bytes:
        return key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    @staticmethod
    def _private_raw(key: Ed25519PrivateKey) -> bytes:
        return key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @staticmethod
    def _key_id(public_raw: bytes) -> str:
        return f"{KEY_ID_PREFIX}-{hashlib.sha256(public_raw).hexdigest()[:16]}"

    @staticmethod
    def _public_b64(public_raw: bytes) -> str:
        return base64.b64encode(public_raw).decode("ascii")

    def _load_private(self) -> Ed25519PrivateKey | None:
        raw_b64 = (self.store.get(PRIVATE_KEY_NAME) or "").strip()
        if not raw_b64:
            return None
        raw = base64.b64decode(raw_b64, validate=True)
        if len(raw) != 32:
            raise RuntimeError("Stored release signing key has invalid length")
        return Ed25519PrivateKey.from_private_bytes(raw)

    def _validate_record(self, key: Ed25519PrivateKey) -> ReleaseSignerStatus:
        public_raw = self._public_raw(key)
        expected_id = self._key_id(public_raw)
        stored_id = (self.store.get(KEY_ID_NAME) or "").strip()
        stored_public = (self.store.get(PUBLIC_KEY_NAME) or "").strip()
        if stored_id and stored_id != expected_id:
            raise RuntimeError("Release signer key-id record does not match private key")
        if stored_public and base64.b64decode(stored_public, validate=True) != public_raw:
            raise RuntimeError("Release signer public record does not match private key")
        created_at = (self.store.get(CREATED_AT_NAME) or "").strip()
        challenge = b"CEO_RELEASE_SIGNER_SELF_TEST_V1"
        sig = key.sign(challenge)
        key.public_key().verify(sig, challenge)
        return ReleaseSignerStatus(
            configured=True,
            key_id=expected_id,
            public_key_b64=self._public_b64(public_raw),
            public_fingerprint=hashlib.sha256(public_raw).hexdigest(),
            created_at=created_at,
            storage="windows-credential-manager+dpapi-backup" if os.name == "nt" else "injected-secret-store",
            self_test=True,
        )

    def status(self) -> ReleaseSignerStatus:
        key = self._load_private()
        if key is None:
            return ReleaseSignerStatus(configured=False, storage="windows-credential-manager+dpapi-backup" if os.name == "nt" else "injected-secret-store")
        return self._validate_record(key)

    def ensure_key(self) -> ReleaseSignerStatus:
        key = self._load_private()
        if key is None:
            key = Ed25519PrivateKey.generate()
            public_raw = self._public_raw(key)
            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            self.store.put(PRIVATE_KEY_NAME, base64.b64encode(self._private_raw(key)).decode("ascii"))
            self.store.put(PUBLIC_KEY_NAME, self._public_b64(public_raw))
            self.store.put(KEY_ID_NAME, self._key_id(public_raw))
            self.store.put(CREATED_AT_NAME, now)
        return self._validate_record(key)

    def rotate_key(self, *, confirmed: bool = False) -> ReleaseSignerStatus:
        if not confirmed:
            raise PermissionError("Release signer rotation requires explicit confirmation")
        key = Ed25519PrivateKey.generate()
        public_raw = self._public_raw(key)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.store.put(PRIVATE_KEY_NAME, base64.b64encode(self._private_raw(key)).decode("ascii"))
        self.store.put(PUBLIC_KEY_NAME, self._public_b64(public_raw))
        self.store.put(KEY_ID_NAME, self._key_id(public_raw))
        self.store.put(CREATED_AT_NAME, now)
        return self._validate_record(key)

    def trusted_public_keys(self) -> dict[str, str]:
        status = self.status()
        return {status.key_id: status.public_key_b64} if status.configured and status.self_test else {}

    def sign_bytes(self, payload: bytes) -> tuple[str, str]:
        key = self._load_private()
        if key is None:
            raise RuntimeError("Release signing authority is not configured")
        status = self._validate_record(key)
        return status.key_id, base64.b64encode(key.sign(payload)).decode("ascii")

    def sign_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = dict(payload)
        row.pop("signature", None)
        row.pop("manifest_fingerprint", None)
        row["signature_alg"] = "ed25519"
        canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        row["manifest_fingerprint"] = hashlib.sha256(canonical).hexdigest()
        # Re-canonicalize with fingerprint excluded, matching updater semantics.
        signed = {k: v for k, v in row.items() if k not in {"signature", "manifest_fingerprint"}}
        signed_bytes = json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        key_id, signature = self.sign_bytes(signed_bytes)
        row["signing_key_id"] = key_id
        # signing_key_id must itself be signed, so sign once more with it present.
        signed = {k: v for k, v in row.items() if k not in {"signature", "manifest_fingerprint"}}
        signed_bytes = json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        row["manifest_fingerprint"] = hashlib.sha256(signed_bytes).hexdigest()
        _, row["signature"] = self.sign_bytes(signed_bytes)
        return row

    def write_public_receipt(self, path: str | Path) -> Path:
        status = self.status()
        if not status.configured:
            raise RuntimeError("Release signing authority is not configured")
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(status)
        payload["private_key_exported"] = False
        tmp = out.with_name(out.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, out)
        return out


def load_local_release_public_keys() -> dict[str, str]:
    if os.name != "nt":
        return {}
    try:
        return ReleaseSigningAuthority().trusted_public_keys()
    except Exception:
        return {}


def memory_authority() -> ReleaseSigningAuthority:
    """Small helper used only by tests/examples; never selected automatically."""
    return ReleaseSigningAuthority(MemorySecretStore())
