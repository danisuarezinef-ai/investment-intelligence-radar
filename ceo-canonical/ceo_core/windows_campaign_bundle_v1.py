from __future__ import annotations

import hashlib
import json
from typing import Any

REQUIRED = (
    "candidate_sha256", "campaign_checkpoint_sha256", "preflight_bundle_sha256",
    "campaign_plan_template_sha256", "fault_matrix_sha256", "recovery_proof_sha256",
)


def _sha(v: Any) -> bool:
    s = str(v or "").strip().lower()
    return len(s) == 64 and all(c in "0123456789abcdef" for c in s)


def _canon(v: Any) -> bytes:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_windows_campaign_bundle_v1(parts: dict[str, Any]) -> dict[str, Any]:
    problems = [k + "_invalid" for k in REQUIRED if not _sha(parts.get(k))]
    row = {
        "schema_version": 1,
        **{k: str(parts.get(k) or "").strip().lower() for k in REQUIRED},
        "single_session": True,
        "resumable": True,
        "physical_evidence_required": True,
        "requires_explicit_human_start": True,
        "automatic_installation": False,
        "automatic_publication": False,
        "automatic_promotion": False,
        "physical_side_effects_executed": False,
    }
    row["campaign_bundle_sha256"] = hashlib.sha256(_canon(row)).hexdigest()
    return {"ok": not problems, "status": "CAMPAIGN_BUNDLE_READY" if not problems else "BLOCKED", "problems": problems, **row}
