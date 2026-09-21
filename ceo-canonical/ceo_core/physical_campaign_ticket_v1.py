from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _canon(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build_physical_campaign_ticket_v1(*, candidate_path: str | Path, candidate_version: str,
                                      baseline: dict[str, Any], policy: str = "one-shot-v1") -> dict[str, Any]:
    package = Path(candidate_path)
    problems: list[str] = []
    if not package.is_file():
        problems.append("candidate_missing")
        digest = ""
        size = 0
    else:
        digest = _sha256_file(package)
        size = package.stat().st_size
    baseline_digest = hashlib.sha256(_canon(baseline)).hexdigest()
    core = {
        "schema_version": 1,
        "candidate_version": str(candidate_version),
        "candidate_name": package.name,
        "candidate_sha256": digest,
        "candidate_size_bytes": size,
        "baseline_sha256": baseline_digest,
        "policy": str(policy),
        "read_only_preparation": True,
        "requires_explicit_human_cutover": True,
        "automatic_installation": False,
        "automatic_publication": False,
        "created_at_epoch": int(time.time()),
    }
    core["ticket_sha256"] = hashlib.sha256(_canon(core)).hexdigest()
    core["ok"] = not problems
    core["problems"] = problems
    return core


def verify_physical_campaign_ticket_v1(ticket: dict[str, Any], *, candidate_path: str | Path,
                                       baseline: dict[str, Any]) -> dict[str, Any]:
    package = Path(candidate_path)
    problems: list[str] = []
    if not package.is_file():
        problems.append("candidate_missing")
    else:
        if _sha256_file(package) != str(ticket.get("candidate_sha256") or ""):
            problems.append("candidate_sha256_mismatch")
        if package.stat().st_size != int(ticket.get("candidate_size_bytes") or 0):
            problems.append("candidate_size_mismatch")
    baseline_digest = hashlib.sha256(_canon(baseline)).hexdigest()
    if baseline_digest != str(ticket.get("baseline_sha256") or ""):
        problems.append("baseline_mismatch")
    core = {k: v for k, v in ticket.items() if k not in {"ticket_sha256", "ok", "problems"}}
    if hashlib.sha256(_canon(core)).hexdigest() != str(ticket.get("ticket_sha256") or ""):
        problems.append("ticket_integrity_mismatch")
    return {"ok": not problems, "problems": problems, "ticket_sha256": ticket.get("ticket_sha256")}
