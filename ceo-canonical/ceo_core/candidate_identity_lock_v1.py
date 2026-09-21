from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any


class CandidateIdentityLockV1:
    """Binds one campaign to one exact candidate package/version without activation authority."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @staticmethod
    def file_sha256(path: str | Path) -> str:
        h = hashlib.sha256()
        with Path(path).open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def create(self, *, package_path: str | Path, version: str, campaign_id: str) -> dict[str, Any]:
        package = Path(package_path)
        if not package.is_file():
            raise FileNotFoundError(str(package))
        row = {
            "schema_version": 1,
            "campaign_id": str(campaign_id),
            "version": str(version),
            "artifact_name": package.name,
            "size_bytes": package.stat().st_size,
            "sha256": self.file_sha256(package),
            "automatic_activation": False,
            "requires_explicit_human_start": True,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        try:
            tmp.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
        return row

    def verify(self, package_path: str | Path, *, expected_version: str | None = None, campaign_id: str | None = None) -> dict[str, Any]:
        try:
            lock = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "problems": [f"lock_unreadable:{type(exc).__name__}"]}
        package = Path(package_path)
        problems: list[str] = []
        if not package.is_file():
            problems.append("package_missing")
        else:
            if int(lock.get("size_bytes") or -1) != package.stat().st_size:
                problems.append("size_mismatch")
            if str(lock.get("sha256") or "").lower() != self.file_sha256(package):
                problems.append("sha256_mismatch")
        if expected_version is not None and str(lock.get("version") or "") != str(expected_version):
            problems.append("version_mismatch")
        if campaign_id is not None and str(lock.get("campaign_id") or "") != str(campaign_id):
            problems.append("campaign_id_mismatch")
        return {"ok": not problems, "problems": problems, "lock": lock}
