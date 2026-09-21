from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_field import FIELD_MISSIONS, SelfHostingFieldOpsCore
from scripts.validate_self_hosting_field import run_supervised_dogfooding

PROJECT_ID = "windows-self-hosting-field"
DESKTOP = Path.home() / "Desktop"
MISSION_RESULT = DESKTOP / "CEO_FIRST_REAL_SUPERVISED_DEV_RESULT.json"
SESSION_RESULT = DESKTOP / "CEO_WORK_SESSION_001_RESULT.json"
LOCAL_RESULTS = ROOT / "RESULTADOS_CEO"

TASK = {
    "work_session": "CEO-WORK-001",
    "kind": "real_supervised_self_improvement",
    "objective": "Add provider-neutral AI worker aliases while preserving legacy field mission identifiers",
    "why_now": "First real supervised task after signed Alpha and Operational Autonomy field validation",
    "human_promotion_required": True,
    "auto_promotion_allowed": False,
    "git_network_allowed": False,
    "auto_spend_allowed": False,
}


def _field_status(core: SelfHostingFieldOpsCore, state, mission: str) -> dict[str, Any]:
    spec = next(x for x in FIELD_MISSIONS if x.mission == mission)
    return core.missions.status(state, spec)


def _load_canonical():
    catalog = ProjectCatalog(user_data_root() / "projects")
    store = catalog.store(PROJECT_ID)
    state = store.load()
    if state is None:
        raise RuntimeError("canonical_project_missing")
    if state.id != PROJECT_ID:
        old = state.id
        history = list(state.metadata.get("project_identity_recovery_v1", []))
        history.append({
            "from": old,
            "to": PROJECT_ID,
            "reason": "work_session_001_canonicalization",
            "repaired_at": datetime.now(timezone.utc).isoformat(),
        })
        state.metadata["project_identity_recovery_v1"] = history[-50:]
        state.id = PROJECT_ID
        store.save(state)
    # Persist once even when the id was already canonical. SqliteCheckpointStore
    # collapses any historical shadow rows here, so subsequent child processes read
    # the same signed Alpha head that this process just verified.
    store.save(state)
    catalog.register(state, make_active=True)
    if catalog.active_project_id() != PROJECT_ID:
        catalog.set_active(PROJECT_ID)
    return catalog, store, state


def _verified_alpha_snapshot() -> dict[str, Any]:
    catalog, store, state = _load_canonical()
    core = SelfHostingFieldOpsCore()
    alpha = _field_status(core, state, "alpha_certification")
    return {
        "verified": alpha.get("verified") is True,
        "status": alpha.get("status"),
        "attestation_verified": bool((alpha.get("attestation") or {}).get("verified")),
        "claims_present": list(alpha.get("claims_present") or []),
        "prerequisites_ok": alpha.get("prerequisites_ok"),
    }


def _ensure_alpha_verified() -> dict[str, Any]:
    """Use the canonical signed Alpha first; historical repair is fallback only.

    This prevents a valid current Alpha from being blocked by the historical recovery
    utility, whose purpose is only to reconstruct missing signed evidence.
    """
    before = _verified_alpha_snapshot()
    if before["verified"] and before["attestation_verified"]:
        return {"source": "canonical_signed_alpha", "before": before, "repair_ran": False, "verified": True}

    repair_script = ROOT / "scripts" / "repair_alpha_evidence.py"
    if not repair_script.is_file():
        return {
            "source": "canonical_signed_alpha",
            "before": before,
            "repair_ran": False,
            "verified": False,
            "error": f"Missing Alpha recovery tool: {repair_script}",
        }

    repair = subprocess.run(
        [sys.executable, str(repair_script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    after = _verified_alpha_snapshot()
    return {
        "source": "historical_recovery_fallback",
        "before": before,
        "repair_ran": True,
        "repair_returncode": int(repair.returncode),
        "repair_stdout_tail": (repair.stdout or "")[-3000:],
        "repair_stderr_tail": (repair.stderr or "")[-3000:],
        "after": after,
        "verified": bool(after["verified"] and after["attestation_verified"]),
    }


def _close_mission_85_after_real_work() -> dict[str, Any]:
    """Attest mission 85 only after a real supervised work session completed PASS."""
    catalog, store, state = _load_canonical()
    core = SelfHostingFieldOpsCore()
    alpha = _field_status(core, state, "alpha_certification")
    if alpha.get("verified") is not True:
        return {"attempted": False, "verified": False, "reason": "alpha_not_verified_after_work"}

    before = _field_status(core, state, "supervised_dogfooding")
    if before.get("verified") is True:
        return {"attempted": False, "verified": True, "reason": "already_verified", "status": before}

    run = run_supervised_dogfooding(core, state)
    store.save(state)
    catalog.register(state, make_active=True)
    after = _field_status(core, state, "supervised_dogfooding")
    return {
        "attempted": True,
        "verified": after.get("verified") is True,
        "run": run,
        "status": after,
    }


def classify_mission_result(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status", "UNKNOWN")).upper()
    pass_status = status == "PASS"
    return {
        "status": "PASS" if pass_status else status,
        "task_completed": pass_status,
        "candidate_created": bool(payload.get("candidate_package") or payload.get("candidate")),
        "requires_human_promotion": True,
        "next": (
            "Review the candidate and evidence; do not promote automatically. Then open the general supervised work intake."
            if pass_status
            else "Inspect the recorded error/blocker, fix only the demonstrated cause, and rerun this same work session."
        ),
    }


def write_session_result(mission_payload: dict[str, Any], *, returncode: int, alpha_gate: dict[str, Any] | None = None, field_85: dict[str, Any] | None = None) -> Path:
    summary = classify_mission_result(mission_payload)
    out = {
        **TASK,
        "runner_returncode": int(returncode),
        "alpha_gate": alpha_gate,
        "mission_result_path": str(MISSION_RESULT),
        "mission_result": mission_payload,
        "field_85": field_85,
        "summary": summary,
        "production_verified": False,
    }
    text = json.dumps(out, indent=2, ensure_ascii=False, default=str)
    targets = [SESSION_RESULT, LOCAL_RESULTS / SESSION_RESULT.name]
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        except Exception:
            pass
    return SESSION_RESULT


def main() -> int:
    if os.name != "nt":
        payload = {"status": "NOT_RUN", "error": "CEO-WORK-001 requires the validated Windows field environment"}
        print(json.dumps({**TASK, **payload}, indent=2, ensure_ascii=False))
        return 2

    try:
        alpha_gate = _ensure_alpha_verified()
    except Exception as exc:
        alpha_gate = {"verified": False, "error": f"{type(exc).__name__}: {exc}"}

    if not alpha_gate.get("verified"):
        payload = {
            "status": "BLOCKED",
            "error": "Canonical signed Alpha is not verified and safe recovery did not restore it",
            "alpha_gate": alpha_gate,
        }
        write_session_result(payload, returncode=3, alpha_gate=alpha_gate)
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 3

    print("[CEO] Canonical signed Alpha VERIFIED. Historical recovery is not required.")
    print("CEO de IAs — WORK SESSION 001")
    print(f"Objective: {TASK['objective']}")
    print("Safety: candidate isolated; no auto-promotion; no Git network; no auto-spend.\n")

    runner = ROOT / "scripts" / "run_first_real_supervised_dev.py"
    if not runner.is_file():
        payload = {"status": "BLOCKED", "error": f"Missing runner: {runner}"}
        write_session_result(payload, returncode=2, alpha_gate=alpha_gate)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2

    proc = subprocess.run([sys.executable, str(runner)], cwd=str(ROOT), check=False)
    try:
        mission_payload = json.loads(MISSION_RESULT.read_text(encoding="utf-8"))
    except Exception as exc:
        mission_payload = {
            "status": "FAILED",
            "error": f"Mission result could not be read: {type(exc).__name__}: {exc}",
        }

    field_85 = None
    if str(mission_payload.get("status", "")).upper() == "PASS":
        try:
            field_85 = _close_mission_85_after_real_work()
        except Exception as exc:
            field_85 = {"attempted": True, "verified": False, "error": f"{type(exc).__name__}: {exc}"}

    out = write_session_result(mission_payload, returncode=proc.returncode, alpha_gate=alpha_gate, field_85=field_85)
    summary = classify_mission_result(mission_payload)
    print("\nWORK SESSION 001 RESULT")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if field_85 is not None:
        print("\nMISSION 85 POST-WORK")
        print(json.dumps({"verified": field_85.get("verified"), "attempted": field_85.get("attempted")}, indent=2, ensure_ascii=False))
    print(f"\nSaved: {out}")
    print(f"Local copy: {LOCAL_RESULTS / SESSION_RESULT.name}")
    return 0 if summary["task_completed"] else (proc.returncode or 1)


if __name__ == "__main__":
    raise SystemExit(main())
