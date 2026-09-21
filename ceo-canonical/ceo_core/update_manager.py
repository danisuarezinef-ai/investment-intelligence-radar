from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx


@dataclass(slots=True)
class UpdateManifest:
    version: str
    url: str
    sha256: str
    channel: str = "stable"
    notes: str = ""


class UpdateManager:
    """Safe update staging primitive.

    CEO may discover and download a newer signed-by-hash package, but this component
    never executes an installer by itself.  Installation is a separate privileged
    action so an update cannot silently replace the running application.
    """

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        clean = value.split("-", 1)[0].replace("rc", ".").replace("dev", ".")
        parts=[]
        for token in clean.split("."):
            digits="".join(c for c in token if c.isdigit())
            parts.append(int(digits or 0))
        return tuple(parts)

    def inspect(self, payload: dict, *, current_version: str) -> dict:
        manifest = UpdateManifest(
            version=str(payload.get("version", "")).strip(),
            url=str(payload.get("url", "")).strip(),
            sha256=str(payload.get("sha256", "")).strip().lower(),
            channel=str(payload.get("channel", "stable")).strip() or "stable",
            notes=str(payload.get("notes", "")),
        )
        if not manifest.version or not manifest.url or len(manifest.sha256) != 64:
            raise ValueError("Invalid update manifest")
        parsed=urlparse(manifest.url)
        if parsed.scheme != "https":
            raise ValueError("Update packages must use HTTPS")
        available=self._version_tuple(manifest.version) > self._version_tuple(current_version)
        return {"available": available, "manifest": manifest}

    async def fetch_manifest(self, url: str, *, current_version: str, client: httpx.AsyncClient | None = None) -> dict:
        if urlparse(url).scheme != "https":
            raise ValueError("Update manifest must use HTTPS")
        owns=client is None; c=client or httpx.AsyncClient(timeout=15)
        try:
            response=await c.get(url); response.raise_for_status(); payload=response.json()
        finally:
            if owns: await c.aclose()
        return self.inspect(payload, current_version=current_version)

    async def stage(self, manifest: UpdateManifest, destination: str | Path, *, client: httpx.AsyncClient | None = None) -> Path:
        destination=Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
        owns=client is None; c=client or httpx.AsyncClient(timeout=120)
        try:
            response=await c.get(manifest.url); response.raise_for_status(); data=response.content
        finally:
            if owns: await c.aclose()
        digest=hashlib.sha256(data).hexdigest()
        if digest.lower()!=manifest.sha256.lower():
            raise ValueError("Downloaded update SHA-256 does not match manifest")
        tmp=destination.with_suffix(destination.suffix+".tmp"); tmp.write_bytes(data); tmp.replace(destination)
        return destination
