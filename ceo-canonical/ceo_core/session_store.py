from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any


class JsonSessionStore:
    """Small persistent registry for browser chat/session identifiers and URLs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._load().get(session_id)

    def put(self, session_id: str, value: dict[str, Any]) -> None:
        with self._lock:
            data = self._load()
            data[session_id] = value
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
