from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .self_dev_handoff import compare_self_development_receipts, validate_self_development_receipt


class SelfDevelopmentInbox:
    """Durable, deduplicated intake for CEO's own self-development receipts."""

    def __init__(self, root: str | Path):
        self.path = Path(root) / "self-development-inbox.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except Exception:
            return []

    def ingest(self, receipt: dict[str, Any]) -> dict[str, Any]:
        verdict = validate_self_development_receipt(receipt)
        if not verdict["ok"]:
            return {"accepted": False, "validation": verdict}
        rows = self._load(); digest = verdict["receipt_sha256"]
        if any(r.get("digest") == digest for r in rows):
            return {"accepted": True, "duplicate": True, "digest": digest}
        row = {"digest": digest, "received_at_epoch": time.time(), "receipt": receipt, "validation": verdict}
        rows.append(row); rows = rows[-500:]
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        return {"accepted": True, "duplicate": False, "digest": digest}

    def compare_latest(self) -> dict[str, Any]:
        rows = self._load()
        if len(rows) < 2:
            return {"comparable": False, "reason": "need_two_valid_receipts"}
        a, b = rows[-2]["receipt"], rows[-1]["receipt"]
        return {"comparable": True, **compare_self_development_receipts(a, b)}

    def snapshot(self) -> dict[str, Any]:
        rows = self._load()
        return {"count": len(rows), "latest": rows[-10:], "auto_promotion": False, "auto_publication": False}
