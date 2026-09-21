from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


SAFE_KINDS = {"analyze", "summarize", "classify", "extract", "compare", "verify_text", "transform_json", "local_test_plan"}


class MobileDevelopmentQueueV2:
    def __init__(self, root: str | Path):
        self.path = Path(root) / "mobile-development-queue-v2.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _id(item: dict[str, Any]) -> str:
        raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()[:24]

    def _load(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8")); return value if isinstance(value, list) else []
        except Exception: return []

    def _save(self, rows: list[dict[str, Any]]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows[-2000:], ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        tmp.replace(self.path)

    def enqueue(self, kind: str, payload: dict[str, Any], *, priority: int = 50, ttl_seconds: int = 86400) -> dict[str, Any]:
        if kind not in SAFE_KINDS: raise PermissionError("mobile development kind is not side-effect-free")
        body = {"kind": kind, "payload": payload, "priority": max(0,min(int(priority),100))}
        item_id = self._id(body); rows = self._load()
        if any(x.get("id") == item_id and x.get("status") in {"queued","leased"} for x in rows):
            return {"accepted": True, "duplicate": True, "id": item_id}
        now=time.time(); rows.append({**body,"id":item_id,"status":"queued","created_at":now,"expires_at":now+max(60,int(ttl_seconds)),"attempts":0,"side_effects_allowed":False})
        self._save(rows); return {"accepted":True,"duplicate":False,"id":item_id}

    def lease(self, *, battery_percent: int = 100, charging: bool = True, thermal: str = "normal", now: float | None = None) -> dict[str, Any] | None:
        epoch=time.time() if now is None else float(now); rows=self._load()
        if str(thermal).lower() in {"hot","critical"} or (not charging and int(battery_percent) < 25): return None
        candidates=[x for x in rows if x.get("status")=="queued" and float(x.get("expires_at") or 0)>epoch and x.get("kind") in SAFE_KINDS and x.get("side_effects_allowed") is False]
        if not candidates: return None
        candidates.sort(key=lambda x:(-int(x.get("priority",0)), float(x.get("created_at",0))))
        chosen=candidates[0]
        for x in rows:
            if x.get("id")==chosen.get("id"):
                x["status"]="leased"; x["leased_at"]=epoch; x["attempts"]=int(x.get("attempts",0))+1; chosen=dict(x); break
        self._save(rows); return chosen

    def complete(self, item_id: str, result_digest: str) -> bool:
        rows=self._load(); changed=False
        for x in rows:
            if x.get("id")==item_id and x.get("status")=="leased":
                x["status"]="done"; x["result_digest"]=str(result_digest); x["completed_at"]=time.time(); changed=True; break
        if changed: self._save(rows)
        return changed

    def snapshot(self) -> dict[str, Any]:
        rows=self._load(); counts={}
        for x in rows: counts[x.get("status","unknown")]=counts.get(x.get("status","unknown"),0)+1
        return {"schema_version":2,"counts":counts,"total":len(rows),"safe_kinds":sorted(SAFE_KINDS),"arbitrary_command_allowed":False,"publication_allowed":False,"installation_allowed":False,"spending_allowed":False}
