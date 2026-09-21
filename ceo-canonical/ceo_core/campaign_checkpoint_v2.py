from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

PHASES = (
    "baseline", "identity_lock", "recovery_point", "stage", "preflight", "human_cutover",
    "launch", "core_health", "productive_smoke", "provider_probe", "complete",
)


class CampaignCheckpointV2:
    def __init__(self, path: str | Path, *, campaign_id: str):
        self.path = Path(path)
        self.campaign_id = str(campaign_id)

    def load(self) -> dict[str, Any]:
        try:
            row = json.loads(self.path.read_text(encoding="utf-8"))
            return row if isinstance(row, dict) else {}
        except Exception:
            return {}

    def record(self, phase: str, *, status: str = "PASS", evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        if phase not in PHASES:
            raise ValueError(f"unknown campaign phase: {phase}")
        if status not in {"PASS", "FAIL", "PENDING"}:
            raise ValueError("invalid checkpoint status")
        row = self.load() or {"schema_version": 2, "campaign_id": self.campaign_id, "records": []}
        if row.get("campaign_id") not in {None, self.campaign_id}:
            raise RuntimeError("campaign checkpoint identity mismatch")
        records = list(row.get("records") or [])
        completed_idx = max((PHASES.index(str(x.get("phase"))) for x in records if x.get("status") == "PASS" and x.get("phase") in PHASES), default=-1)
        idx = PHASES.index(phase)
        if status == "PASS" and idx > completed_idx + 1:
            raise RuntimeError("campaign phase order violation")
        item = {"phase": phase, "status": status, "recorded_at_epoch": time.time(), "evidence": evidence or {}}
        records.append(item)
        row.update({"campaign_id": self.campaign_id, "records": records, "current_phase": phase, "current_status": status})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        try:
            tmp.write_text(json.dumps(row, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
        return row

    def resumable_state(self) -> dict[str, Any]:
        row = self.load()
        passed = {str(x.get("phase")) for x in row.get("records", []) if x.get("status") == "PASS"}
        next_phase = next((p for p in PHASES if p not in passed), "complete")
        return {"campaign_id": self.campaign_id, "passed": sorted(passed, key=PHASES.index), "next_phase": next_phase, "complete": next_phase == "complete" and "complete" in passed}
