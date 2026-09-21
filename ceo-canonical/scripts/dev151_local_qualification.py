from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.android_artifact_identity_v1 import build_android_artifact_identity_v1
from ceo_core.android_reproducible_build_v1 import qualify_android_build_inputs_v1, compare_debug_build_receipts_v1
from ceo_core.android_runtime_dossier_v2 import qualify_runtime_dossier_v2
from ceo_core.authority_boundary_v2 import qualify_authority_boundary_v2
from ceo_core.campaign_checkpoint_v1 import build_campaign_checkpoint_v1, verify_campaign_checkpoint_v1
from ceo_core.campaign_resume_guard_v2 import qualify_campaign_resume_v2
from ceo_core.one_shot_preflight_bundle_v1 import build_one_shot_preflight_bundle_v1
from ceo_core.physical_campaign_plan_v6 import build_one_shot_windows_campaign_v6
from ceo_core.physical_evidence_schema_v1 import PHYSICAL_GATES, blank_physical_evidence_set_v1
from ceo_core.recovery_proof_v1 import bounded_recovery_proof_v1
from ceo_core.release_readiness_v12 import qualify_release_v12
from ceo_core.shared_core_contract_v3 import validate_shared_core_contract_v3
from ceo_core.soak_guard_v7 import run_soak_guard_v7
from ceo_core.tree_manifest_v1 import build_tree_manifest
from ceo_core.update_fault_matrix_v1 import build_update_fault_matrix_v1
from ceo_core.update_model_checker_v5 import bounded_model_check_v5
from ceo_core.windows_campaign_bundle_v1 import build_windows_campaign_bundle_v1

BASE_VERSION = "1.4.18-rc1-physical-readiness"
BASE_ARTIFACT_SHA256 = "4d17c113f15036dce0419c279ab7b20488aa523ca03b9c257bfa936de674f4e0"
CANDIDATE_VERSION = "1.4.28-rc1-first-artifact-readiness"


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _sha_json(value: object) -> str:
    return _sha_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _shared_contract() -> dict:
    return {
        "shared_core_protocol": 2,
        "platforms": ["windows", "android"],
        "shared_features": ["task_exchange", "evidence_exchange", "update_metadata", "capability_manifest"],
        "schemas": {"task": 1, "evidence": 3, "mobile_sync": 4, "update_metadata": 2},
        "platform_ui_independent": True,
        "platform_packaging_independent": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--soak-seeds", type=int, default=1800)
    ap.add_argument("--soak-steps", type=int, default=220)
    ap.add_argument("--transfer-rounds", type=int, default=5000)
    ap.add_argument("--ledger-rounds", type=int, default=2000)
    ap.add_argument("--checkpoint-rounds", type=int, default=3000)
    ap.add_argument("--resume-rounds", type=int, default=3000)
    ns = ap.parse_args()

    out: dict[str, object] = {
        "base_version": BASE_VERSION,
        "candidate_version": CANDIDATE_VERSION,
        "windows_update_freeze_respected": True,
    }

    descriptor = _read_json(ROOT / "schemas" / "ANDROID_BUILD_INPUTS_DEV21.json")
    lock_path = ROOT / "schemas" / "android_dev21" / "TOOLCHAIN.lock.json"
    manifest_path = ROOT / "schemas" / "android_dev21" / "BUILD_PAYLOAD_MANIFEST.json"
    validation_path = ROOT / "schemas" / "android_dev21" / "DEV21_CLEAN_VALIDATION.json"
    runtime_gate_path = ROOT / "schemas" / "android_dev21" / "DEV21_A181_A190_GATE.json"
    lock = _read_json(lock_path)
    manifest = _read_json(manifest_path)
    validation = _read_json(validation_path)
    runtime_gate = _read_json(runtime_gate_path)
    evidence_hashes_ok = all((
        _sha_file(lock_path) == descriptor["toolchain_lock_sha256"],
        _sha_file(manifest_path) == descriptor["build_manifest_sha256"],
        _sha_file(validation_path) == descriptor["clean_validation_sha256"],
        _sha_file(runtime_gate_path) == descriptor["runtime_gate_sha256"],
        validation.get("build_payload_sha256") == descriptor["build_payload_sha256"],
        validation.get("source_fingerprint") == descriptor["source_fingerprint"],
        validation.get("clean_zip_pytest") == "194/194 PASS",
        runtime_gate.get("status") == "RUNTIME_HARDENING_HARNESS_READY",
        runtime_gate.get("runtime_api35_executed") is False,
        runtime_gate.get("runtime_api36_executed") is False,
    ))
    out["android_dev21_evidence_chain"] = {
        "ok": evidence_hashes_ok,
        "payload_files": descriptor["payload_files"],
        "build_payload_sha256": descriptor["build_payload_sha256"],
        "runtime_harness_ready": runtime_gate.get("status") == "RUNTIME_HARDENING_HARNESS_READY",
        "runtime_api35_executed": False,
        "runtime_api36_executed": False,
        "production_verified": False,
    }

    build_inputs = qualify_android_build_inputs_v1(lock, manifest, expected_payload_sha256=descriptor["build_payload_sha256"])
    out["android_reproducible_build_v1"] = build_inputs

    identity = build_android_artifact_identity_v1(
        source_fingerprint=descriptor["source_fingerprint"],
        build_payload_sha256=descriptor["build_payload_sha256"],
        build_manifest_sha256=descriptor["build_manifest_sha256"],
        toolchain_lock_sha256=descriptor["toolchain_lock_sha256"],
        version_code=descriptor["version_code"],
        package_name=descriptor["package_name"],
    )
    out["android_artifact_identity_v1"] = identity
    # Deliberately incomplete: no APK exists in this checkpoint.
    incomplete_build_check = compare_debug_build_receipts_v1({}, {})
    out["android_dual_build_status"] = {
        "status": "NOT_EXECUTED",
        "contract_rejects_missing_builds": not incomplete_build_check["ok"],
        "apk_built": False,
        "reproducibility_verified": False,
    }
    pending_runtime = qualify_runtime_dossier_v2({}, {})
    out["android_runtime_dossier_v2"] = {
        "contract_rejects_missing_runtime": not pending_runtime["ok"],
        "status": "NOT_EXECUTED",
        "android_runtime_accepted": False,
        "production_verified": False,
    }

    shared = validate_shared_core_contract_v3(_shared_contract())
    out["shared_core_contract_v3"] = shared

    tree = build_tree_manifest(ROOT, include_prefixes=("ceo_core", "ceo_app", "scripts", "schemas"), max_files=5000, max_file_bytes=16_000_000)
    tree_sha = tree["root_digest"]
    out["current_tree"] = {"root_digest": tree_sha, "file_count": tree["file_count"], "total_bytes": sum(int(x["size"]) for x in tree["files"])}

    blank = blank_physical_evidence_set_v1(tree_sha)
    checkpoint = build_campaign_checkpoint_v1(campaign_id="dev151-plan", candidate_sha256=tree_sha, evidence=blank)
    checkpoint_verify = verify_campaign_checkpoint_v1(checkpoint)
    resume = qualify_campaign_resume_v2(candidate_sha256=tree_sha, evidence=blank, expected_candidate_sha256=tree_sha)
    skipped = [dict(x) for x in blank]
    skipped[1].update({"status": "PASS", "source": "physical_windows", "observed_at": "2026-09-17T00:00:00Z"})
    resume_skip_rejected = not qualify_campaign_resume_v2(candidate_sha256=tree_sha, evidence=skipped, expected_candidate_sha256=tree_sha)["ok"]
    out["campaign_resume_guard_v2"] = {
        "blank_resume": resume,
        "skipped_gate_rejected": resume_skip_rejected,
        "ok": bool(resume["ok"] and resume["next_gate"] == PHYSICAL_GATES[0] and resume_skip_rejected),
    }

    preflight = build_one_shot_preflight_bundle_v1(
        base_artifact_sha256=BASE_ARTIFACT_SHA256,
        candidate_tree_sha256=tree_sha,
        android_source_sha256=descriptor["source_fingerprint"],
        android_sbom_sha256=descriptor["sbom_sha256"],
        shared_contract_sha256=shared["contract_sha256"],
        physical_schema_sha256=_sha_file(ROOT / "ceo_core" / "physical_evidence_schema_v1.py"),
        campaign_checkpoint_sha256=checkpoint["checkpoint_sha256"],
    )
    out["one_shot_preflight_bundle_v1"] = preflight

    faults = build_update_fault_matrix_v1()
    recovery = bounded_recovery_proof_v1()
    out["update_fault_matrix_v1"] = faults
    out["recovery_proof_v1"] = recovery

    campaign_bundle = build_windows_campaign_bundle_v1({
        "candidate_sha256": tree_sha,
        "campaign_checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "preflight_bundle_sha256": preflight["bundle_sha256"],
        "campaign_plan_template_sha256": _sha_file(ROOT / "ceo_core" / "physical_campaign_plan_v6.py"),
        "fault_matrix_sha256": _sha_json(faults),
        "recovery_proof_sha256": _sha_json(recovery),
    })
    out["windows_campaign_bundle_v1"] = campaign_bundle

    authority = qualify_authority_boundary_v2([
        "read_files", "write_sandbox", "run_tests", "run_benchmarks", "local_http_health",
        "browser_navigation", "terminal_bounded", "collect_evidence", "build_debug_artifact", "read_only_mobile_sync",
    ])
    unsafe_authority = qualify_authority_boundary_v2(["run_tests", "automatic_installation", "payments", "real_trading"])
    out["authority_boundary_v2"] = {
        "safe": authority,
        "forbidden_request_rejected": not unsafe_authority["ok"],
        "ok": authority["ok"] and not unsafe_authority["ok"],
    }

    model = bounded_model_check_v5(max_depth=17)
    out["update_model_checker_v5"] = model

    local_preconditions = {
        "dev141_continuity": True,
        "android_artifact_identity": bool(identity["ok"] and evidence_hashes_ok),
        "android_build_inputs": bool(build_inputs["ok"]),
        "android_runtime_dossier_contract": bool(not pending_runtime["ok"]),
        "windows_campaign_bundle": bool(campaign_bundle["ok"]),
        "campaign_resume_guard": bool(out["campaign_resume_guard_v2"]["ok"]),
        "authority_boundary": bool(out["authority_boundary_v2"]["ok"]),
        "model_checker_v5": bool(model["ok"]),
    }
    campaign = build_one_shot_windows_campaign_v6(
        local_preconditions, candidate_sha256=tree_sha, campaign_bundle_sha256=campaign_bundle["campaign_bundle_sha256"]
    )
    out["physical_campaign_plan_v6"] = campaign

    soak = run_soak_guard_v7(
        seeds=ns.soak_seeds, steps=ns.soak_steps, transfer_rounds=ns.transfer_rounds,
        ledger_rounds=ns.ledger_rounds, checkpoint_rounds=ns.checkpoint_rounds, resume_rounds=ns.resume_rounds,
    )
    out["soak_guard_v7"] = soak

    gates = {
        "dev141_ready": True,
        "android_artifact_identity": bool(identity["ok"] and evidence_hashes_ok),
        "android_build_inputs": bool(build_inputs["ok"]),
        "android_runtime_dossier_contract": bool(not pending_runtime["ok"]),
        "windows_campaign_bundle": bool(campaign_bundle["ok"]),
        "campaign_resume_guard": bool(out["campaign_resume_guard_v2"]["ok"]),
        "authority_boundary": bool(out["authority_boundary_v2"]["ok"]),
        "model_checker_v5": bool(model["ok"]),
        "campaign_plan_v6": bool(campaign["ready_for_human_start_review"] and campaign["mode"] == "plan_only"),
        "soak_guard_v7": bool(soak["ok"]),
    }
    readiness = qualify_release_v12(
        gates, windows_physical_verified=False, android_debug_apk_built=False,
        android_debug_apk_reproducible=False, android_runtime_accepted=False, human_release_authorized=False,
    )
    out["release_readiness_v12"] = readiness
    out["ok"] = bool(
        readiness["local_candidate_ready"] and readiness["windows_campaign_bundle_ready"]
        and readiness["android_first_debug_apk_build_kit_ready"]
        and not readiness["android_debug_apk_built"] and not readiness["android_debug_apk_reproducible"]
        and not readiness["windows_physical_verified"] and not readiness["android_runtime_accepted"]
        and not readiness["production_ready"] and readiness["windows_update_freeze_respected"]
        and checkpoint["ok"] and checkpoint_verify["ok"]
    )

    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.json:
        Path(ns.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if out["ok"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
