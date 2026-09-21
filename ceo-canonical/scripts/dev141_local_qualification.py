from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.android_build_readiness_v1 import qualify_android_build_readiness_v1
from ceo_core.campaign_checkpoint_v1 import build_campaign_checkpoint_v1, verify_campaign_checkpoint_v1
from ceo_core.capability_drift_guard_v1 import compare_capability_manifests_v1
from ceo_core.one_shot_preflight_bundle_v1 import build_one_shot_preflight_bundle_v1
from ceo_core.physical_campaign_plan_v5 import build_one_shot_windows_campaign_v5
from ceo_core.physical_evidence_schema_v1 import blank_physical_evidence_set_v1, validate_physical_evidence_v1
from ceo_core.recovery_proof_v1 import bounded_recovery_proof_v1
from ceo_core.release_readiness_v11 import qualify_release_v11
from ceo_core.soak_guard_v6 import run_soak_guard_v6
from ceo_core.tree_manifest_v1 import build_tree_manifest
from ceo_core.update_fault_matrix_v1 import build_update_fault_matrix_v1
from ceo_core.update_model_checker_v4 import bounded_model_check_v4

BASE_VERSION = "1.4.7-rc1-cross-platform-preflight"
BASE_ARTIFACT_SHA256 = "92cd593f575e37d3e211f48011180fb56b25e9e3caaa4257b11d6e111de10d51"
CANDIDATE_VERSION = "1.4.18-rc1-physical-readiness"

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


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--soak-seeds", type=int, default=1800)
    ap.add_argument("--soak-steps", type=int, default=220)
    ap.add_argument("--transfer-rounds", type=int, default=5000)
    ap.add_argument("--ledger-rounds", type=int, default=2000)
    ap.add_argument("--checkpoint-rounds", type=int, default=3000)
    ns = ap.parse_args()

    out: dict[str, object] = {
        "base_version": BASE_VERSION,
        "candidate_version": CANDIDATE_VERSION,
        "windows_update_freeze_respected": True,
    }
    tree = build_tree_manifest(ROOT, include_prefixes=("ceo_core", "ceo_app", "scripts"), max_files=5000, max_file_bytes=16_000_000)
    tree_sha = tree["root_digest"]
    out["current_tree"] = {"root_digest": tree_sha, "file_count": tree["file_count"], "total_bytes": sum(int(x["size"]) for x in tree["files"])}

    blank = blank_physical_evidence_set_v1(tree_sha)
    physical_schema_ok = all(validate_physical_evidence_v1(x)["ok"] for x in blank)
    fake_physical_claim = validate_physical_evidence_v1({
        "gate": "baseline_health", "status": "PASS", "source": "plan_only", "candidate_sha256": tree_sha, "observed_at": "2026-09-17T00:00:00Z"
    })
    out["physical_evidence_schema_v1"] = {
        "ok": physical_schema_ok and not fake_physical_claim["ok"],
        "blank_records": len(blank),
        "fake_physical_claim_rejected": not fake_physical_claim["ok"],
        "fake_claim_problems": fake_physical_claim["problems"],
    }

    checkpoint = build_campaign_checkpoint_v1(campaign_id="dev141-local-plan", candidate_sha256=tree_sha, evidence=blank)
    checkpoint_verify = verify_campaign_checkpoint_v1(checkpoint)
    out["campaign_checkpoint_v1"] = {"checkpoint": checkpoint, "verification": checkpoint_verify}

    android = qualify_android_build_readiness_v1(ANDROID_EVIDENCE)
    out["android_build_readiness_v1"] = android

    shared_contract_sha = _file_sha(ROOT / "ceo_core" / "shared_core_contract_v3.py")
    physical_schema_sha = _file_sha(ROOT / "ceo_core" / "physical_evidence_schema_v1.py")
    bundle = build_one_shot_preflight_bundle_v1(
        base_artifact_sha256=BASE_ARTIFACT_SHA256,
        candidate_tree_sha256=tree_sha,
        android_source_sha256=ANDROID_EVIDENCE["source_fingerprint"],
        android_sbom_sha256=ANDROID_EVIDENCE["sbom_sha256"],
        shared_contract_sha256=shared_contract_sha,
        physical_schema_sha256=physical_schema_sha,
        campaign_checkpoint_sha256=checkpoint["checkpoint_sha256"],
    )
    out["one_shot_preflight_bundle_v1"] = bundle

    faults = build_update_fault_matrix_v1()
    recovery = bounded_recovery_proof_v1()
    out["update_fault_matrix_v1"] = faults
    out["recovery_proof_v1"] = recovery

    baseline_caps = ["task_exchange", "evidence_exchange", "update_metadata", "capability_manifest"]
    candidate_caps = baseline_caps + ["campaign_checkpoint", "physical_evidence_schema", "android_build_readiness"]
    drift = compare_capability_manifests_v1(baseline_caps, candidate_caps)
    drift_adversarial = compare_capability_manifests_v1(baseline_caps, candidate_caps + ["auto_install", "spending"])
    out["capability_drift_guard_v1"] = {
        "safe_candidate": drift,
        "adversarial_rejected": not drift_adversarial["ok"],
        "adversarial_sensitive_added": drift_adversarial["sensitive_added"],
        "ok": drift["ok"] and not drift_adversarial["ok"],
    }

    model = bounded_model_check_v4(max_depth=16)
    out["update_model_checker_v4"] = model

    local_preconditions = {
        "dev130_continuity": True,
        "physical_evidence_schema": bool(out["physical_evidence_schema_v1"]["ok"]),
        "campaign_checkpoint": bool(checkpoint["ok"] and checkpoint_verify["ok"]),
        "one_shot_preflight_bundle": bool(bundle["ok"]),
        "android_first_build_ready": bool(android["ok"]),
        "fault_matrix": bool(faults["ok"]),
        "recovery_proof": bool(recovery["ok"]),
        "capability_drift_guard": bool(out["capability_drift_guard_v1"]["ok"]),
        "model_checker_v4": bool(model["ok"]),
    }
    campaign = build_one_shot_windows_campaign_v5(local_preconditions, candidate_sha256=tree_sha)
    out["physical_campaign_plan_v5"] = campaign

    soak = run_soak_guard_v6(
        seeds=ns.soak_seeds, steps=ns.soak_steps, transfer_rounds=ns.transfer_rounds,
        ledger_rounds=ns.ledger_rounds, checkpoint_rounds=ns.checkpoint_rounds,
    )
    out["soak_guard_v6"] = soak

    gates = {
        "dev130_ready": True,
        "physical_evidence_schema": bool(out["physical_evidence_schema_v1"]["ok"]),
        "campaign_checkpoint": bool(checkpoint["ok"] and checkpoint_verify["ok"]),
        "one_shot_preflight_bundle": bool(bundle["ok"]),
        "android_first_build_ready": bool(android["ok"]),
        "fault_matrix": bool(faults["ok"]),
        "recovery_proof": bool(recovery["ok"]),
        "capability_drift_guard": bool(out["capability_drift_guard_v1"]["ok"]),
        "model_checker_v4": bool(model["ok"]),
        "campaign_plan_v5": bool(campaign["ready_for_human_start_review"] and campaign["mode"] == "plan_only"),
        "soak_guard_v6": bool(soak["ok"]),
    }
    readiness = qualify_release_v11(gates, windows_physical_verified=False, android_runtime_accepted=False, human_release_authorized=False)
    out["release_readiness_v11"] = readiness
    out["ok"] = bool(
        readiness["local_candidate_ready"] and readiness["physical_campaign_package_ready"]
        and readiness["android_first_debug_apk_build_ready"] and not readiness["windows_physical_verified"]
        and not readiness["android_runtime_accepted"] and not readiness["production_ready"]
        and readiness["windows_update_freeze_respected"]
    )

    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.json:
        Path(ns.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if out["ok"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
