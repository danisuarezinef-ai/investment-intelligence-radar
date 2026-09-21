from __future__ import annotations

import json
import subprocess
from pathlib import Path


class SandboxRecovery:
    """Restore only an explicitly marked disposable CEO sandbox."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        marker = self.root / "CEO_B19_SANDBOX.json"
        if not marker.is_file():
            raise ValueError("sandbox marker missing")
        row = json.loads(marker.read_text(encoding="utf-8"))
        if not row.get("sandbox") or row.get("production"):
            raise ValueError("workspace is not an approved disposable sandbox")
        remotes = subprocess.run(
            ["git", "remote"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()
        if remotes:
            raise ValueError("sandbox recovery refuses repositories with remotes")
        self.baseline = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()

    def restore_baseline(self) -> str:
        subprocess.run(
            ["git", "reset", "--hard", self.baseline],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        current = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()
        if current != self.baseline:
            raise RuntimeError("sandbox baseline restore failed")
        diff = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()
        if diff:
            raise RuntimeError("sandbox is not clean after restore")
        return current
