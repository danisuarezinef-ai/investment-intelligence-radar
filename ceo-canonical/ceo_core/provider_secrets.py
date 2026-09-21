from __future__ import annotations

import os
from dataclasses import dataclass

from .credentials import WindowsCredentialManagerStore


_PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
_PROVIDER_CRED = {
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
}


@dataclass(slots=True)
class ProviderSecretStatus:
    provider: str
    configured: bool
    source: str | None


def _store() -> WindowsCredentialManagerStore | None:
    if os.name != "nt":
        return None
    try:
        return WindowsCredentialManagerStore(namespace="CEO-de-IAs")
    except Exception:
        return None


def resolve_provider_secret(provider: str) -> str | None:
    provider = provider.lower().strip()
    env_name = _PROVIDER_ENV.get(provider)
    if not env_name:
        return None
    env_value = os.getenv(env_name)
    if env_value:
        return env_value
    store = _store()
    if store is None:
        return None
    try:
        return store.get(_PROVIDER_CRED[provider]) or None
    except Exception:
        return None


def provider_secret_status() -> list[ProviderSecretStatus]:
    rows: list[ProviderSecretStatus] = []
    store = _store()
    for provider, env_name in _PROVIDER_ENV.items():
        if os.getenv(env_name):
            rows.append(ProviderSecretStatus(provider, True, "environment"))
            continue
        configured = False
        if store is not None:
            try:
                configured = bool(store.get(_PROVIDER_CRED[provider]))
            except Exception:
                configured = False
        rows.append(ProviderSecretStatus(provider, configured, "windows-credential-manager" if configured else None))
    return rows


def save_provider_secret(provider: str, value: str) -> ProviderSecretStatus:
    provider = provider.lower().strip()
    if provider not in _PROVIDER_CRED:
        raise ValueError("Unsupported provider")
    value = value.strip()
    if not value:
        raise ValueError("API key cannot be empty")
    store = _store()
    if store is None:
        raise RuntimeError("Persistent provider credentials are available only through Windows Credential Manager on Windows")
    store.put(_PROVIDER_CRED[provider], value)
    return ProviderSecretStatus(provider, True, "windows-credential-manager")


def delete_provider_secret(provider: str) -> None:
    provider = provider.lower().strip()
    if provider not in _PROVIDER_CRED:
        raise ValueError("Unsupported provider")
    store = _store()
    if store is None:
        raise RuntimeError("Persistent provider credentials are available only on Windows")
    store.delete(_PROVIDER_CRED[provider])
