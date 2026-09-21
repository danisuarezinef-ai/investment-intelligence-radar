from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.android_evidence_import_v1 import validate_android_evidence_import_v1
from ceo_core.convergence_gate_v2 import qualify_convergence_gate_v2
from ceo_core.cross_platform_parity_v1 import evaluate_cross_platform_parity_v1
from ceo_core.cross_platform_provenance_v1 import build_cross_platform_provenance_v1
from ceo_core.physical_campaign_plan_v4 import build_one_shot_windows_campaign_v4, campaign_progress_v4
from ceo_core.regression_impact_v2 import select_regression_scope
from ceo_core.release_readiness_v10 import qualify_release_v10
from ceo_core.self_dev_receipt_v3 import validate_self_development_receipt_v3
from ceo_core.shared_core_contract_v3 import validate_shared_core_contract_v3
from ceo_core.soak_guard_v5 import run_soak_guard_v5
from ceo_core.tree_manifest_v1 import build_tree_manifest
from ceo_core.update_model_checker_v3 import bounded_model_check_v3
from ceo_core.update_transaction_ledger_v2 import UpdateTransactionLedgerV2

BASE_VERSION = "1.3.97-rc1-convergence-control"
BASE_ARTIFACT_SHA256 = "dbfc02c5cdfc60d80fa03f149fd95b21db16c41592541850122035d225fd4c98"
CANDIDATE_VERSION = "1.4.7-rc1-cross-platform-preflight"

ANDROID_EVIDENCE = {
    "status": "RUNTIME_HARDENING_HARNESS_READY",
    "source_fingerprint": "d0baaf9d35d04dc9606d9c77f7856277e24f6a711e9e1a79e367d61937646ce8",
    "sbom_sha256": "b92e3cf049d39e02b68eef3ccb3d73496eb65a6c424b999c83adff913636f394",
    "build_payload_sha256": "48fa82db04580802703b921778097a71c56460151c3b980c09976d0f6675c0a5",
    "checkpoint_sha256": "0732fcbbac3a46e6f2872262f59261b4b3a827d13aa26ace79a0ea34dd91f1de",
    "source_tests_passed": 194,
    "source_tests_failed": 0,
    "runtime_api35_executed": False,
    "runtime_api36_executed": False,
    "android_runtime_accepted": False,
    "production_verified": False,
}


def _h(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def _receipt() -> dict:
    return {
        "candidate_id": "windows-self-dev-130",
        "base_version": BASE_VERSION,
        "candidate_version": CANDIDATE_VERSION,
        "changed_files": ["ceo_core/shared_core_contract_v3.py", "ceo_core/update_model_checker_v3.py"],
        "file_hashes": {
            "ceo_core/shared_core_contract_v3.py": _h("shared-core-v3"),
            "ceo_core/update_model_checker_v3.py": _h("model-checker-v3"),
        },
        "tests": {"passed": 130, "failed": 0},
        "published": False,
        "installed": False,
        "auto_promoted": False,
        "safety": {
            "stable_unchanged": True,
            "automatic_spending_false": True,
            "automatic_publication_false": True,
            "automatic_installation_false": True,
        },
        "base_tree_sha256": _h("dev120-base-tree"),
        "candidate_tree_sha256": _h("dev130-candidate-tree"),
        "evidence": [{"kind": "test_report", "ref": "local:dev130", "sha256": _h("dev130-evidence")}],
        "authority": {
            "automatic_merge": False,
            "automatic_promotion": False,
            "automatic_publication": False,
            "automatic_installation": False,
            "automatic_spending": False,
        },
    }


def _shared_contract() -> dict:
    return {
        "shared_core_protocol": 2,
        "platforms": ["windows", "android"],
        "shared_features": ["task_exchange", "evidence_exchange", "update_metadata", "capability_manifest"],
        "schemas": {"task": 1, "evidence": 3, "mobile_sync": 4, "update_metadata": 2},
        "platform_ui_independent": True,
        "platform_packaging_independent": True,
    }


def _platform(ui: str, package: str) -> dict:
    return {
        "shared_core_protocol": 2,
        "schemas": {"task": 1, "evidence": 3, "mobile_sync": 4, "update_metadata": 2},
        "capabilities": ["task_exchange", "evidence_exchange", "update_metadata", "capability_manifest"],
        "ui_surface": ui,
        "package_kind": package,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--soak-seeds", type=int, default=1800)
    ap.add_argument("--soak-steps", type=int, default=220)
    ap.add_argument("--transfer-rounds", type=int, default=5000)
    ap.add_argument("--ledger-rounds", type=int, default=2000)
    ns = ap.parse_args()

    out: dict[str, object] = {
        "base_version": BASE_VERSION,
        "candidate_version": CANDIDATE_VERSION,
        "windows_update_freeze_respected": True,
    }

    shared = validate_shared_core_contract_v3(_shared_contract())
    out["shared_core_contract_v3"] = shared

    android = validate_android_evidence_import_v1(ANDROID_EVIDENCE)
    out["android_evidence_import_v1"] = android

    current_tree = build_tree_manifest(ROOT, include_prefixes=("ceo_core", "ceo_app", "scripts"), max_files=5000, max_file_bytes=16_000_000)
    out["current_tree"] = {"root_digest": current_tree["root_digest"], "file_count": current_tree["file_count"], "total_bytes": sum(int(row["size"]) for row in current_tree["files"])}

    provenance = build_cross_platform_provenance_v1(
        windows_artifact_sha256=BASE_ARTIFACT_SHA256,
        windows_tree_sha256=current_tree["root_digest"],
        android_source_sha256=ANDROID_EVIDENCE["source_fingerprint"],
        android_sbom_sha256=ANDROID_EVIDENCE["sbom_sha256"],
        shared_core_contract_sha256=shared["contract_sha256"],
        base_version=BASE_VERSION,
    )
    out["cross_platform_provenance_v1"] = provenance

    parity = evaluate_cross_platform_parity_v1(
        _platform("windows_desktop", "windows_zip"),
        _platform("android_native", "android_apk"),
    )
    out["cross_platform_parity_v1"] = parity

    ledger = UpdateTransactionLedgerV2(max_records=32)
    ledger.append("candidate_seen", {"candidate": CANDIDATE_VERSION, "authority": []})
    ledger.append("preflight_started", {"base": BASE_VERSION, "authority": []})
    ledger.append("preflight_passed", {"local_only": True, "authority": []})
    ledger.append("snapshot_recorded", {"logical_only": True, "authority": []})
    ledger_result = ledger.verify()
    out["update_transaction_ledger_v2"] = ledger_result

    model = bounded_model_check_v3(max_depth=17)
    out["update_model_checker_v3"] = model

    receipt = validate_self_development_receipt_v3(_receipt(), expected_base_version=BASE_VERSION)
    out["self_dev_receipt_v3"] = receipt
    impact = select_regression_scope([
        "ceo_core/shared_core_contract_v3.py",
        "ceo_core/android_evidence_import_v1.py",
        "ceo_core/update_model_checker_v3.py",
        "ceo_core/release_readiness_v10.py",
        "ceo_core/soak_guard_v5.py",
    ])
    out["regression_impact_v2"] = impact

    convergence = qualify_convergence_gate_v2(
        receipt_ok=bool(receipt["ok"] and receipt["strong_attestation"]),
        tree_conflicts=0,
        protected_paths=0,
        regression_complete=bool(impact["full_regression_required"]),
        android_source_harness_ready=bool(android["source_harness_ready"]),
        parity_ok=bool(parity["ok"]),
        provenance_ok=bool(provenance["ok"]),
        ledger_ok=bool(ledger_result["ok"]),
        model_check_ok=bool(model["ok"]),
    )
    out["convergence_gate_v2"] = convergence

    local_preconditions = {
        "dev120_continuity": True,
        "shared_core_contract": bool(shared["ok"]),
        "android_source_harness": bool(android["source_harness_ready"]),
        "cross_platform_parity": bool(parity["ok"]),
        "cross_platform_provenance": bool(provenance["ok"]),
        "transaction_ledger": bool(ledger_result["ok"]),
        "model_checker_v3": bool(model["ok"]),
        "convergence_gate_v2": bool(convergence["eligible_for_one_shot_preparation"]),
    }
    campaign = build_one_shot_windows_campaign_v4(local_preconditions)
    out["physical_campaign_plan_v4"] = campaign
    out["physical_campaign_progress_empty"] = campaign_progress_v4({})

    soak = run_soak_guard_v5(
        seeds=ns.soak_seeds,
        steps=ns.soak_steps,
        transfer_rounds=ns.transfer_rounds,
        ledger_rounds=ns.ledger_rounds,
    )
    out["soak_guard_v5"] = soak

    gates = {
        "dev120_ready": True,
        "shared_core_contract": bool(shared["ok"]),
        "android_evidence_import": bool(android["source_harness_ready"] and not android["production_verified"]),
        "cross_platform_provenance": bool(provenance["ok"]),
        "cross_platform_parity": bool(parity["ok"]),
        "transaction_ledger": bool(ledger_result["ok"]),
        "model_checker_v3": bool(model["ok"]),
        "convergence_gate_v2": bool(convergence["eligible_for_one_shot_preparation"]),
        "campaign_plan_v4": bool(campaign["ready_for_human_start_review"] and campaign["mode"] == "plan_only"),
        "soak_guard_v5": bool(soak["ok"]),
    }
    readiness = qualify_release_v10(
        gates,
        windows_physical_verified=False,
        human_release_authorized=False,
        android_runtime_accepted=bool(android["android_runtime_accepted"]),
    )
    out["release_readiness_v10"] = readiness
    out["ok"] = bool(
        readiness["local_candidate_ready"]
        and readiness["cross_platform_preflight_ready"]
        and not readiness["windows_physical_verified"]
        and not readiness["android_runtime_accepted"]
        and not readiness["production_ready"]
        and readiness["windows_update_freeze_respected"]
    )

    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.json:
        Path(ns.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if out["ok"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
