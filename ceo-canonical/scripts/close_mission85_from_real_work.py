from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_beta import FrictionDetector, SelfHostingBetaCore, SupervisedUseTracker
from ceo_core.self_hosting_field import FIELD_MISSIONS, SelfHostingFieldOpsCore
from scripts.validate_self_hosting_field import run_supervised_dogfooding

PROJECT_ID = "windows-self-hosting-field"
DESKTOP = Path.home() / "Desktop"
LOCAL_RESULTS = ROOT / "RESULTADOS_CEO"
RESULT = DESKTOP / "CEO_MISSION_85_CLOSURE_RESULT.json"


def status(core, state, mission: str):
    spec = next(x for x in FIELD_MISSIONS if x.mission == mission)
    return core.missions.status(state, spec)


def save_result(payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    try:
        DESKTOP.mkdir(parents=True, exist_ok=True)
        RESULT.write_text(text, encoding="utf-8")
    except Exception:
        pass
    try:
        LOCAL_RESULTS.mkdir(parents=True, exist_ok=True)
        (LOCAL_RESULTS / RESULT.name).write_text(text, encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    if os.name != "nt":
        payload = {"status": "NOT_RUN", "reason": "windows_field_environment_required"}
        save_result(payload); print(json.dumps(payload, indent=2)); return 2
    catalog = ProjectCatalog(user_data_root() / "projects")
    store = catalog.store(PROJECT_ID)
    state = store.load()
    if state is None:
        payload = {"status": "BLOCKED", "reason": "canonical_project_missing"}
        save_result(payload); print(json.dumps(payload, indent=2)); return 3
    core = SelfHostingFieldOpsCore()
    alpha = status(core, state, "alpha_certification")
    if not alpha.get("verified") or not (alpha.get("attestation") or {}).get("verified"):
        payload = {"status": "BLOCKED", "reason": "signed_alpha_not_verified", "alpha": alpha}
        save_result(payload); print(json.dumps(payload, indent=2, default=str)); return 4

    beta = SelfHostingBetaCore()
    sessions = list(state.metadata.get(SupervisedUseTracker.KEY, {}).values())
    field_sessions = [s for s in sessions if s.get("status") == "COMPLETE" and s.get("field_verified")]
    if not field_sessions:
        payload = {"status": "BLOCKED", "reason": "no_completed_field_supervised_session"}
        save_result(payload); print(json.dumps(payload, indent=2)); return 5

    # Re-measure friction from the real completed session.  Zero open items is a valid
    # measurement and is persisted as an empty list rather than being treated as absent.
    latest = sorted(field_sessions, key=lambda x: float(x.get("completed_at") or 0))[-1]
    state.metadata.setdefault(FrictionDetector.KEY, [])
    open_rows = beta.friction.backlog(state)
    state.metadata["self_hosting_friction_measurement_v1"] = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "session_id": latest.get("session_id"),
        "open_avoidable": len(open_rows),
        "zero_is_valid_measurement": True,
        "source": "real_work_session_001",
    }
    # Refresh objective metrics from the persisted real field session before attesting 85.
    metrics = beta.metrics.measure(state)
    store.save(state)

    before = status(core, state, "supervised_dogfooding")
    if before.get("verified"):
        payload = {"status": "PASS", "mission_85_verified": True, "already_verified": True,
                   "friction_measurement": state.metadata["self_hosting_friction_measurement_v1"], "metrics": metrics}
        save_result(payload); print(json.dumps(payload, indent=2, default=str)); return 0

    run = run_supervised_dogfooding(core, state)
    store.save(state)
    catalog.register(state, make_active=True)
    # Prove persistence through a clean reload.
    reloaded = store.load()
    if reloaded is None:
        payload = {"status": "BLOCKED", "reason": "reload_failed_after_85"}
        save_result(payload); print(json.dumps(payload, indent=2)); return 6
    after = status(SelfHostingFieldOpsCore(), reloaded, "supervised_dogfooding")
    payload = {
        "status": "PASS" if after.get("verified") else "BLOCKED",
        "mission_85_verified": bool(after.get("verified")),
        "before": before,
        "run": run,
        "after": after,
        "friction_measurement": reloaded.metadata.get("self_hosting_friction_measurement_v1"),
        "metrics": beta.metrics.measure(reloaded),
        "production_verified": False,
    }
    save_result(payload); print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0 if after.get("verified") else 7


if __name__ == "__main__":
    raise SystemExit(main())
