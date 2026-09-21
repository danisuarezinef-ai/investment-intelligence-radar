from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


class CampaignEvidenceChainV1:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.records: list[dict[str, Any]] = []
        if self.path.is_file():
            try:
                row = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(row, list): self.records = row
            except Exception: self.records = []

    def append(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        seq = len(self.records) + 1
        prev = self.records[-1]["hash"] if self.records else "0" * 64
        body = {"seq": seq, "kind": str(kind), "payload": payload, "prev": prev}
        body["hash"] = hashlib.sha256(_canon(body)).hexdigest()
        self.records.append(body)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
        return dict(body)

    def verify(self) -> dict[str, Any]:
        prev = "0" * 64; problems: list[str] = []
        for i, rec in enumerate(self.records, 1):
            if int(rec.get("seq") or 0) != i: problems.append(f"seq:{i}")
            if str(rec.get("prev") or "") != prev: problems.append(f"prev:{i}")
            body = {"seq": rec.get("seq"), "kind": rec.get("kind"), "payload": rec.get("payload"), "prev": rec.get("prev")}
            expected = hashlib.sha256(_canon(body)).hexdigest()
            if str(rec.get("hash") or "") != expected: problems.append(f"hash:{i}")
            prev = str(rec.get("hash") or "")
        return {"ok": not problems, "records": len(self.records), "head_sha256": prev, "problems": problems, "append_only": True}
