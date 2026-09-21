from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.android_packaging_contract_v1 import validate_android_packaging_manifest
from ceo_core.convergence_evidence_matrix_v1 import qualify_convergence_evidence
from ceo_core.convergence_sandbox_v2 import build_convergence_sandbox_plan
from ceo_core.mobile_sync_v4 import MobileSyncV4
from ceo_core.physical_campaign_plan_v3 import build_one_shot_windows_campaign_v3, campaign_progress
from ceo_core.regression_impact_v2 import select_regression_scope
from ceo_core.release_readiness_v9 import qualify_release_v9
from ceo_core.self_dev_receipt_v3 import validate_self_development_receipt_v3
from ceo_core.soak_guard_v4 import run_soak_guard_v4
from ceo_core.tree_manifest_v1 import build_tree_manifest
from ceo_core.update_model_checker_v2 import bounded_model_check_v2

BASE_VERSION = "1.3.87-rc1-convergence-reliability"


def _h(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def _receipt() -> dict:
    return {
        "candidate_id": "windows-self-dev-120",
        "base_version": BASE_VERSION,
        "candidate_version": "windows-self-dev-120-candidate",
        "changed_files": ["ceo_core/quality_gate.py"],
        "file_hashes": {"ceo_core/quality_gate.py": _h("quality-v2")},
        "tests": {"passed": 100, "failed": 0},
        "published": False, "installed": False, "auto_promoted": False,
        "safety": {"stable_unchanged": True, "automatic_spending_false": True, "automatic_publication_false": True, "automatic_installation_false": True},
        "base_tree_sha256": _h("base-tree"), "candidate_tree_sha256": _h("candidate-tree"),
        "evidence": [{"kind": "test_report", "ref": "windows:self-dev:test", "sha256": _h("evidence")}],
        "authority": {"automatic_merge": False, "automatic_promotion": False, "automatic_publication": False, "automatic_installation": False, "automatic_spending": False},
    }


def _tree_fixture(root: Path, quality: str, scheduler: str) -> dict:
    (root / "ceo_core").mkdir(parents=True, exist_ok=True)
    (root / "ceo_core" / "quality_gate.py").write_text(quality, encoding="utf-8")
    (root / "ceo_core" / "scheduler.py").write_text(scheduler, encoding="utf-8")
    return build_tree_manifest(root, include_prefixes=("ceo_core",))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--soak-seeds", type=int, default=1200)
    ap.add_argument("--soak-steps", type=int, default=200)
    ap.add_argument("--transfer-rounds", type=int, default=3000)
    ns = ap.parse_args()
    out: dict[str, object] = {}

    receipt = validate_self_development_receipt_v3(_receipt(), expected_base_version=BASE_VERSION)
    out["receipt_v3"] = receipt

    with tempfile.TemporaryDirectory(prefix="dev120-tree-") as td:
        base_dir = Path(td) / "base"; win_dir = Path(td) / "windows"; mob_dir = Path(td) / "mobile"
        base = _tree_fixture(base_dir, "quality=1", "scheduler=1")
        windows = _tree_fixture(win_dir, "quality=2", "scheduler=1")
        mobile = _tree_fixture(mob_dir, "quality=1", "scheduler=2")
        plan = build_convergence_sandbox_plan(base, windows, mobile)
        out["tree_manifest"] = {"base": base["root_digest"], "windows": windows["root_digest"], "mobile": mobile["root_digest"], "file_counts": [base["file_count"], windows["file_count"], mobile["file_count"]]}
        out["convergence_sandbox"] = plan

    impact = select_regression_scope(["ceo_core/in_app_updater.py", "ceo_core/mobile_sync_v4.py"])
    out["regression_impact"] = impact
    out["evidence_matrix"] = qualify_convergence_evidence(
        receipt_ok=receipt["ok"], strong_attestation=receipt["strong_attestation"], tree_conflicts=len(plan["blocked_paths"]), protected_paths=0,
        tests_passed=100, tests_failed=0, benchmark_complete=True, regression_scope_complete=impact["full_regression_required"],
    )

    key = os.urandom(32); sender = MobileSyncV4(key); receiver = MobileSyncV4(key)
    envs = sender.issue_transfer([{"kind": "status", "payload": {"i": i}} for i in range(137)], chunk_size=23)
    verified = receiver.verify_transfer(envs)
    replay_rejected = False
    try:
        receiver.verify_transfer(envs)
    except PermissionError:
        replay_rejected = True
    out["mobile_sync_v4"] = {"items": len(verified["items"]), "chunks": verified["chunks_verified"], "replay_rejected": replay_rejected, "side_effects_allowed": verified["side_effects_allowed"]}

    packaging = validate_android_packaging_manifest({
        "application_id": "com.ceodeias.app", "version_name": "0.1.0", "version_code": 1,
        "single_install_package": True, "in_app_updates": True, "manual_post_install_configuration_required": False,
        "shared_core_protocol": 2, "requested_privileged_capabilities": [],
    })
    out["android_packaging"] = packaging
    out["model_checker_v2"] = bounded_model_check_v2(max_depth=15)
    campaign = build_one_shot_windows_campaign_v3(); out["campaign_plan_v3"] = campaign
    out["campaign_progress_empty"] = campaign_progress({})
    out["soak_guard_v4"] = run_soak_guard_v4(seeds=ns.soak_seeds, steps=ns.soak_steps, transfer_rounds=ns.transfer_rounds)

    gates = {
        "dev110_ready": True,
        "receipt_v3": bool(receipt["ok"] and receipt["strong_attestation"]),
        "tree_manifest": bool(out["tree_manifest"]["file_counts"] == [2, 2, 2]),
        "convergence_sandbox": bool(not plan["blocked_paths"] and plan["stable_mutation_allowed"] is False),
        "regression_impact": bool(impact["full_regression_required"] and "FULL_REGRESSION" in impact["required_suites"]),
        "evidence_matrix": bool(out["evidence_matrix"]["state"] == "ELIGIBLE_FOR_SANDBOX_COMPARISON"),
        "mobile_sync_v4": bool(len(verified["items"]) == 137 and replay_rejected and verified["side_effects_allowed"] is False),
        "android_packaging": bool(packaging["ok"]),
        "model_checker_v2": bool(out["model_checker_v2"]["ok"]),
        "campaign_plan_v3": bool(campaign["single_physical_session"] and campaign["mode"] == "plan_only" and campaign["automatic_installation"] is False),
        "soak_guard_v4": bool(out["soak_guard_v4"]["ok"]),
    }
    out["readiness"] = qualify_release_v9(gates, windows_physical_verified=False, human_release_authorized=False)
    out["ok"] = bool(out["readiness"]["local_candidate_ready"] and not out["readiness"]["production_ready"] and out["readiness"]["windows_update_freeze_respected"])
    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.json: Path(ns.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if out["ok"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
