from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import shutil
import tempfile
from typing import Any, Iterable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackupRecoveryV2:
    """Content-addressed project-data snapshots with verify-before-restore semantics."""

    EXCLUDED_NAMES = {".remote_hmac", "private.key", "release-private.key"}
    EXCLUDED_PARTS = {"secrets", "browser_profiles", "credentials"}

    @classmethod
    def _allowed(cls, rel: Path) -> bool:
        if rel.name.lower() in cls.EXCLUDED_NAMES:
            return False
        return not any(part.lower() in cls.EXCLUDED_PARTS for part in rel.parts)

    @staticmethod
    def _hash(path: Path) -> str:
        h = sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def create(self, source_root: str | Path, backup_root: str | Path, *, label: str = "snapshot") -> dict[str, Any]:
        source = Path(source_root).resolve(); backups = Path(backup_root).resolve(); backups.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snap = backups / f"{stamp}-{sha256((str(source)+label+stamp).encode()).hexdigest()[:8]}"
        tmp = Path(tempfile.mkdtemp(prefix="ceo-backup-", dir=backups))
        files = {}
        try:
            for path in source.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(source)
                if not self._allowed(rel):
                    continue
                target = tmp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                files[rel.as_posix()] = {"sha256": self._hash(target), "size": target.stat().st_size}
            manifest = {"schema": 2, "created_at": _now(), "source": str(source), "label": label, "files": files}
            (tmp / "BACKUP_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, snap)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True); raise
        return {"path": str(snap), "files": len(files), "manifest_sha256": self._hash(snap / "BACKUP_MANIFEST.json")}

    def verify(self, snapshot: str | Path) -> dict[str, Any]:
        root = Path(snapshot); manifest_path = root / "BACKUP_MANIFEST.json"
        if not manifest_path.exists():
            return {"valid": False, "errors": ["missing_manifest"]}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")); errors = []
        for rel, meta in (manifest.get("files") or {}).items():
            path = root / rel
            if not path.is_file(): errors.append(f"missing:{rel}"); continue
            if path.stat().st_size != int(meta.get("size", -1)): errors.append(f"size:{rel}"); continue
            if self._hash(path) != meta.get("sha256"): errors.append(f"hash:{rel}")
        return {"valid": not errors, "errors": errors[:100], "files": len(manifest.get("files") or {})}

    def restore(self, snapshot: str | Path, destination: str | Path, *, confirm: bool = False) -> dict[str, Any]:
        if not confirm:
            raise PermissionError("restore requires explicit confirmation")
        verified = self.verify(snapshot)
        if not verified["valid"]:
            raise ValueError(f"invalid snapshot: {verified['errors'][:3]}")
        source = Path(snapshot); dest = Path(destination)
        if dest.exists() and any(dest.iterdir()):
            raise FileExistsError("restore destination must be empty to avoid destructive overwrite")
        dest.mkdir(parents=True, exist_ok=True)
        manifest = json.loads((source / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
        for rel in manifest["files"]:
            target = dest / rel; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source / rel, target)
        return {"restored": True, "files": len(manifest["files"]), "destination": str(dest)}
