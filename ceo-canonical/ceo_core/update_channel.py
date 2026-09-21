from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class UpdateChannelIdentity:
    product_id: str
    channel: str
    manifest_url: str
    bootstrap_transport: str = ""
    intended_repository: str = ""


def _trust_payload() -> dict[str, Any]:
    path = Path(__file__).with_name("update_trust.json")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def official_channel() -> UpdateChannelIdentity:
    """Return the built-in update channel identity.

    The endpoint is data-driven rather than hard-coded in the UI or installer.  A
    release can therefore migrate transport hosts without rebuilding the updater
    logic.  CEO_UPDATE_MANIFEST_URL remains an explicit operator override.
    """
    payload = _trust_payload()
    channel = payload.get("channel") if isinstance(payload.get("channel"), dict) else {}
    manifest_url = os.getenv("CEO_UPDATE_MANIFEST_URL", "").strip() or str(channel.get("manifest_url") or "").strip()
    parsed = urlparse(manifest_url) if manifest_url else None
    if manifest_url and (parsed is None or parsed.scheme.lower() != "https"):
        manifest_url = ""
    return UpdateChannelIdentity(
        product_id=str(channel.get("product_id") or "ceo-de-ias"),
        channel=str(channel.get("name") or "stable"),
        manifest_url=manifest_url,
        bootstrap_transport=str(channel.get("bootstrap_transport") or ""),
        intended_repository=str(channel.get("intended_repository") or ""),
    )
