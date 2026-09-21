from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


class CampaignExactlyOnceGuardV1:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> dict[str, Any]:
        try:
            row = json.loads(self.path.read_text(encoding="utf-8"))
            return row if isinstance(row, dict) else {}
        except Exception:
            return {}

    def claim(self, *, campaign_id: str, candidate_sha256: str) -> dict[str, Any]:
        current = self._load()
        if current:
            same = current.get("campaign_id") == campaign_id and current.get("candidate_sha256") == candidate_sha256
            return {"ok": same, "claimed": False, "duplicate": same, "conflict": not same, "record": current}
        row = {"campaign_id": campaign_id, "candidate_sha256": candidate_sha256, "token": uuid.uuid4().hex,
               "status": "claimed", "cutover_count": 0}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(row, f, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, self.path)
        return {"ok": True, "claimed": True, "duplicate": False, "conflict": False, "record": row}

    def record_cutover(self, *, token: str) -> dict[str, Any]:
        row = self._load()
        if not row or row.get("token") != token:
            return {"ok": False, "reason": "token_mismatch"}
        count = int(row.get("cutover_count") or 0)
        if count >= 1:
            return {"ok": True, "performed": False, "duplicate_blocked": True, "cutover_count": count}
        row["cutover_count"] = 1; row["status"] = "cutover_recorded"
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(row, f, sort_keys=True); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, self.path)
        return {"ok": True, "performed": True, "duplicate_blocked": False, "cutover_count": 1}
