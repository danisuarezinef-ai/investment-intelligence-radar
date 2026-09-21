from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _canon(v: Any) -> bytes:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class EvidenceBridgeV1:
    """Append-only provenance bridge for mobile/Windows development receipts."""
    def __init__(self, root: str | Path):
        self.path=Path(root)/"development-evidence-bridge.json"; self.path.parent.mkdir(parents=True,exist_ok=True)

    def _load(self):
        try:
            v=json.loads(self.path.read_text(encoding="utf-8")); return v if isinstance(v,list) else []
        except Exception:return []

    def append(self, source: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if source not in {"mobile","windows","development"}: raise ValueError("unsupported evidence source")
        rows=self._load(); prev=str(rows[-1].get("event_hash") if rows else "")
        event={"source":source,"kind":str(kind),"payload_digest":hashlib.sha256(_canon(payload)).hexdigest(),"prev_hash":prev,"timestamp":time.time()}
        event["event_hash"]=hashlib.sha256(_canon(event)).hexdigest(); rows.append(event)
        tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps(rows[-5000:],indent=2,sort_keys=True)+"\n",encoding="utf-8"); tmp.replace(self.path)
        return event

    def verify(self) -> dict[str, Any]:
        rows=self._load(); prev=""
        for i,row in enumerate(rows):
            if str(row.get("prev_hash") or "") != prev: return {"ok":False,"index":i,"reason":"prev_hash_mismatch"}
            copy={k:v for k,v in row.items() if k!="event_hash"}; expected=hashlib.sha256(_canon(copy)).hexdigest()
            if str(row.get("event_hash") or "") != expected: return {"ok":False,"index":i,"reason":"event_hash_mismatch"}
            prev=expected
        return {"ok":True,"events":len(rows),"last_hash":prev,"mutating_authority":False}
