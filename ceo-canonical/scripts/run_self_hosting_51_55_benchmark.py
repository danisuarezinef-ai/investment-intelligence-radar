from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState
from ceo_core.self_hosting_beta import SelfHostingBetaCore, SupervisedStep


def run() -> dict:
    core = SelfHostingBetaCore()
    state = ProjectState(goal="benchmark self-hosting beta")

    # 100 synthetic supervised sessions / 2,000 logical steps.
    for sidx in range(100):
        session = core.usage.start_session(state, label=f"synthetic-{sidx}", field_executed=False, platform="benchmark")
        for i in range(20):
            core.usage.record_step(state, session["session_id"], SupervisedStep(
                action=f"task-{i}", success=True, autonomous=True,
                recovery_attempted=(i % 10 == 0), recovery_success=True if i % 10 == 0 else None,
            ))
        core.complete_session(state, session["session_id"])

    synthetic_metrics = core.metrics.measure(state)
    synthetic_permission = core.permissions.recommend(state)
    beta = core.gate.assess(state)

    # Separate fixture exercises the positive permission path without claiming real field evidence.
    fixture = ProjectState(goal="permission fixture")
    fixture_core = SelfHostingBetaCore()
    for idx in range(3):
        session = fixture_core.usage.start_session(
            fixture, label=f"fixture-field-{idx}", field_executed=True,
            platform="SIMULATED_FIELD_FIXTURE", evidence=[f"fixture:{idx}"],
        )
        for i in range(10):
            fixture_core.usage.record_step(fixture, session["session_id"], SupervisedStep(action=f"fixture-{i}", success=True, autonomous=True))
        fixture_core.complete_session(fixture, session["session_id"])
    rec = fixture_core.permissions.recommend(fixture)
    applied = fixture_core.permissions.apply(fixture, target="supervised", human_confirmed=True, actor="human")
    after = fixture_core.permissions.recommend(fixture)

    # Friction: one intervention must surface as an issue and prevent graduation.
    friction_state = ProjectState(goal="friction fixture")
    friction_core = SelfHostingBetaCore()
    session = friction_core.usage.start_session(friction_state, label="friction", field_executed=False)
    friction_core.usage.record_step(friction_state, session["session_id"], SupervisedStep(
        action="manual handoff", success=True, autonomous=False, human_intervention=True,
        friction=["manual_transfer"],
    ))
    friction_core.complete_session(friction_state, session["session_id"])
    backlog = friction_core.friction.backlog(friction_state)

    checks = {
        "synthetic_sessions_100": len(core.usage.sessions(state)) == 100,
        "synthetic_steps_2000": synthetic_metrics["steps"] == 2000,
        "synthetic_scope_not_field": synthetic_metrics["evidence_scope"] == "SYNTHETIC",
        "synthetic_cannot_increase_permissions": synthetic_permission["eligible_for_increase"] is False,
        "beta_local_prepared": beta["status"] == "BETA_PREPARED_LOCAL" and beta["ready"] is False,
        "permission_positive_path_fixture": rec["eligible_for_increase"] is True and applied["mode"] == "supervised",
        "evidence_not_reused_after_graduation": after["eligible_for_increase"] is False and "field_evidence_required_at_current_permission_level" in after["reasons"],
        "avoidable_intervention_becomes_friction": any(x["kind"] == "human_intervention" for x in backlog),
        "production_verified_false": beta["production_verified"] is False,
    }
    return {
        "benchmark": "SELF_HOSTING_51_55",
        "pass": all(checks.values()),
        "checks": checks,
        "synthetic_metrics": synthetic_metrics,
        "synthetic_permission": synthetic_permission,
        "beta_gate": beta,
        "permission_fixture": {
            "explicitly_synthetic": True,
            "before": rec,
            "applied": applied,
            "after": after,
        },
        "friction_fixture": {"explicitly_synthetic": True, "open_items": len(backlog), "top": backlog[:5]},
        "windows_physical": "DEFERRED_BY_USER",
        "live_provider": "NOT_VERIFIED",
        "production_verified": False,
    }


if __name__ == "__main__":
    result = run()
    out = ROOT / "reports" / "SELF_HOSTING_51_55_BENCHMARK.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"pass": result["pass"], "checks": result["checks"]}, indent=2))
    raise SystemExit(0 if result["pass"] else 1)
