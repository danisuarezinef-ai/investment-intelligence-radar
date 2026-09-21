from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

_SECRET_RE = re.compile(r"(?i)(token|secret|password|private[_-]?key|api[_-]?key|authorization)")


def _redact(value: Any, key: str = "") -> Any:
    if _SECRET_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value[:200]]
    if isinstance(value, str):
        value = re.sub(r"(?i)[A-Z]:\\Users\\[^\\]+", r"%USERPROFILE%", value)
        return value[:4000]
    return value


class UpdateFailureEvidenceRecorderV1:
    """Durable, redacted evidence for update failures and recovery decisions."""

    def __init__(self, updates_root: str | Path):
        self.root = Path(updates_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.latest = self.root / "update-failure-latest.json"
        self.history = self.root / "update-failure-history.jsonl"

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        tmp = path.with_name(path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True, default=str)
                fh.write("\n")
                fh.flush(); os.fsync(fh.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def record(self, phase: str, *, outcome: str, reason: str = "", **fields: Any) -> dict[str, Any]:
        row = _redact({
            "schema_version": 1,
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "recorded_at_epoch": time.time(),
            "phase": str(phase),
            "outcome": str(outcome),
            "reason": str(reason)[:2000],
            "production_verified": False,
            **fields,
        })
        self._atomic_json(self.latest, row)
        with self.history.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
            fh.flush(); os.fsync(fh.fileno())
        return row
