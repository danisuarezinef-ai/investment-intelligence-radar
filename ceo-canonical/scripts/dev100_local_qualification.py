from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.android_contract_v1 import android_contract_v1, validate_android_request
from ceo_core.compatibility_matrix_v1 import assess_compatibility
from ceo_core.evidence_bridge_v1 import EvidenceBridgeV1
from ceo_core.executive_snapshot_v2 import build_executive_snapshot
from ceo_core.mobile_dev_queue_v2 import MobileDevelopmentQueueV2
from ceo_core.release_readiness_v7 import qualify_release_v7
from ceo_core.self_dev_reconciler import reconcile_self_development
from ceo_core.soak_guard_v2 import run_soak_guard_v2
from ceo_core.update_failure_lab_v3 import UpdateFailureLabV3
from ceo_core.update_recovery_planner_v2 import plan_update_recovery


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--soak-seeds", type=int, default=1000)
    ap.add_argument("--soak-steps", type=int, default=200)
    ns = ap.parse_args()

    out: dict[str, object] = {}

    external = {
        "candidate_id": "windows-self-dev-001",
        "base_version": "1.3.47",
        "candidate_version": "windows-self-dev-candidate",
        "changed_files": ["ceo_core/scheduler.py", "ceo_core/quality_gate.py"],
        "tests": {"passed": 20, "failed": 0},
        "published": False,
        "installed": False,
        "auto_promoted": False,
        "safety": {
            "stable_unchanged": True,
            "automatic_spending_false": True,
            "automatic_publication_false": True,
            "automatic_installation_false": True,
        },
    }
    mobile_files = [
        "ceo_core/self_dev_reconciler.py", "ceo_core/update_failure_lab_v3.py",
        "ceo_core/scheduler.py", "ceo_core/android_contract_v1.py",
    ]
    out["self_dev_reconciliation"] = reconcile_self_development(external, mobile_files, mobile_candidate_id="dev100")

    out["failure_lab_v3"] = UpdateFailureLabV3.campaign(seeds=ns.soak_seeds, steps=ns.soak_steps)

    recovery_cases = {
        "healthy": plan_update_recovery({"phase": "healthy", "current_healthy": True}),
        "pending_unhealthy": plan_update_recovery({"phase": "activating", "pending_health": True, "current_healthy": False}),
        "journal_bad": plan_update_recovery({"phase": "staged", "journal_ok": False}),
        "preflight_failed": plan_update_recovery({"phase": "preflight_failed"}),
    }
    out["recovery_planner"] = recovery_cases

    with tempfile.TemporaryDirectory(prefix="ceo-dev100-") as td:
        q = MobileDevelopmentQueueV2(td)
        first = q.enqueue("compare", {"left": "a", "right": "b"}, priority=80)
        duplicate = q.enqueue("compare", {"left": "a", "right": "b"}, priority=80)
        low = q.enqueue("summarize", {"text": "x"}, priority=20)
        thermal_block = q.lease(battery_percent=90, charging=True, thermal="hot")
        lease = q.lease(battery_percent=90, charging=True, thermal="normal")
        completed = bool(lease and q.complete(str(lease["id"]), "sha256:synthetic"))
        forbidden = False
        try:
            q.enqueue("shell", {"cmd": "whoami"})
        except PermissionError:
            forbidden = True
        out["mobile_queue"] = {
            "first": first, "duplicate": duplicate, "low": low,
            "thermal_blocked": thermal_block is None, "leased": lease,
            "completed": completed, "forbidden_rejected": forbidden,
            "snapshot": q.snapshot(),
        }

        bridge = EvidenceBridgeV1(td)
        e1 = bridge.append("windows", "development_receipt", external)
        e2 = bridge.append("mobile", "candidate_summary", {"id": "dev100", "files": mobile_files})
        bridge_ok = bridge.verify()
        # Deliberate tamper must be detected.
        p = Path(td) / "development-evidence-bridge.json"
        rows = json.loads(p.read_text(encoding="utf-8")); rows[0]["payload_digest"] = "0" * 64
        p.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tamper = bridge.verify()
        out["evidence_bridge"] = {"event1": e1, "event2": e2, "before_tamper": bridge_ok, "after_tamper": tamper}

    contract = android_contract_v1()
    out["android_contract"] = {
        "contract": contract,
        "safe_status": validate_android_request("status_summary"),
        "forbidden_shell": validate_android_request("arbitrary_shell"),
        "forbidden_payment": validate_android_request("payment"),
    }

    out["executive_snapshot"] = build_executive_snapshot({
        "goal": "Mejorar CEO de IAs", "progress_percent": 72.4,
        "active_workers": 2, "target_workers": 4, "eta_seconds": 900,
        "completed": 87, "human_decisions": 0, "autonomous_recoveries": 1,
        "now": "Validando candidata", "next": "Comparar evidencia de autoevolución",
    })

    out["compatibility"] = {
        "same": assess_compatibility({"data_schema": 1, "package_contract": 1, "sync_protocol": 2}, {"data_schema": 1, "package_contract": 1, "sync_protocol": 2}),
        "forward_one": assess_compatibility({"data_schema": 1, "package_contract": 1, "sync_protocol": 2}, {"data_schema": 2, "package_contract": 1, "sync_protocol": 2}),
        "unsafe_jump": assess_compatibility({"data_schema": 1, "package_contract": 1, "sync_protocol": 2}, {"data_schema": 4, "package_contract": 1, "sync_protocol": 2}),
    }

    out["soak_guard_v2"] = run_soak_guard_v2(seeds=max(100, ns.soak_seeds // 2), steps=ns.soak_steps)

    gates = {
        "dev90_ready": True,
        "self_dev_reconciler": out["self_dev_reconciliation"]["requires_human_merge_decision"] is True and out["self_dev_reconciliation"]["automatic_merge"] is False,
        "failure_lab_v3": bool(out["failure_lab_v3"]["ok"]),
        "recovery_planner_v2": recovery_cases["pending_unhealthy"]["recommended_action"] == "rollback_to_last_known_good" and recovery_cases["pending_unhealthy"]["allows_cutover"] is False,
        "mobile_queue_v2": bool(out["mobile_queue"]["duplicate"]["duplicate"] and out["mobile_queue"]["thermal_blocked"] and out["mobile_queue"]["completed"] and out["mobile_queue"]["forbidden_rejected"]),
        "android_contract_v1": bool(out["android_contract"]["safe_status"]["allowed"] and not out["android_contract"]["forbidden_shell"]["allowed"] and contract["manual_post_install_configuration_required"] is False),
        "evidence_bridge_v1": bool(out["evidence_bridge"]["before_tamper"]["ok"] and not out["evidence_bridge"]["after_tamper"]["ok"]),
        "executive_snapshot_v2": out["executive_snapshot"]["hero"]["state"] == "RECUPERANDO" and out["executive_snapshot"]["technical_details_collapsed"] is True,
        "compatibility_matrix_v1": bool(out["compatibility"]["same"]["compatible"] and out["compatibility"]["forward_one"]["compatible"] and not out["compatibility"]["unsafe_jump"]["compatible"]),
        "soak_guard_v2": bool(out["soak_guard_v2"]["ok"]),
    }
    out["readiness"] = qualify_release_v7(gates, windows_physical_verified=False, human_release_authorized=False)
    out["ok"] = bool(out["readiness"]["local_candidate_ready"] and not out["readiness"]["production_ready"] and not out["readiness"]["publication_allowed"] and not out["readiness"]["installation_allowed"])

    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.json:
        Path(ns.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if out["ok"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
