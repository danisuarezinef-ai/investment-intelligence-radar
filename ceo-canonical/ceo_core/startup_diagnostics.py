from __future__ import annotations

import json
import os
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from .runtime import user_data_root


class StartupDiagnostics:
    """One durable startup/health diagnostic stream per user profile.

    It is deliberately independent from the source/install directory so an update
    or uninstall cannot erase the evidence needed to understand a failed launch.
    """

    def __init__(self, data_root: str | Path | None = None):
        base = Path(data_root) if data_root else user_data_root()
        self.root = base / "diagnostics"
        self.root.mkdir(parents=True, exist_ok=True)
        self.latest_path = self.root / "startup-latest.json"
        self.history_path = self.root / "startup-history.jsonl"
        self.failure_path = self.root / "startup-latest-error.txt"

    @staticmethod
    def _atomic_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def record(self, status: str, **fields: Any) -> dict[str, Any]:
        row = {
            "status": str(status),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "production_verified": False,
            **fields,
        }
        text = json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
        self._atomic_text(self.latest_path, text)
        with self.history_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return row

    def exception(self, exc: BaseException, **fields: Any) -> dict[str, Any]:
        detail = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
        self._atomic_text(self.failure_path, detail)
        return self.record("BLOCKED", error=str(exc), error_type=type(exc).__name__, failure_file=str(self.failure_path), **fields)
