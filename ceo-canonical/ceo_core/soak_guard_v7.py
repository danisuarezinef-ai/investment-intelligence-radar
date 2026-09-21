from __future__ import annotations

import hashlib
import json
from typing import Any

from .android_artifact_identity_v1 import build_android_artifact_identity_v1
from .android_reproducible_build_v1 import qualify_android_build_inputs_v1, compare_debug_build_receipts_v1
from .android_runtime_dossier_v2 import qualify_runtime_dossier_v2
from .authority_boundary_v2 import qualify_authority_boundary_v2
from .campaign_resume_guard_v2 import qualify_campaign_resume_v2
from .physical_evidence_schema_v1 import PHYSICAL_GATES, blank_physical_evidence_set_v1
from .soak_guard_v6 import run_soak_guard_v6
from .update_model_checker_v5 import bounded_model_check_v5
from .windows_campaign_bundle_v1 import build_windows_campaign_bundle_v1


def _sha_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _synthetic_manifest() -> dict[str, Any]:
    files = [{"path": f"file-{i:02d}", "sha256": hashlib.sha256(f"file-{i}".encode()).hexdigest(), "size": i + 1} for i in range(45)]
    return {"files": files, "minimal_source_sha256": "a" * 64, "production_verified": False}


def _synthetic_lock() -> dict[str, Any]:
    return {
        "jdk": "17", "gradle": "9.4.1", "android_gradle_plugin": "9.2.1", "compile_sdk": 37,
        "target_sdk": 37, "min_sdk": 26, "chaquopy": "17.0.0", "python_runtime": "3.13",
        "kotlin_compose_plugin": "2.3.21", "ci_emulator_api_levels": [35, 36], "abis": ["arm64-v8a", "x86_64"],
    }


def run_soak_guard_v7(*, seeds: int = 1800, steps: int = 220, transfer_rounds: int = 5000,
                      ledger_rounds: int = 2000, checkpoint_rounds: int = 3000,
                      resume_rounds: int = 3000) -> dict[str, Any]:
    base = run_soak_guard_v6(
        seeds=seeds, steps=steps, transfer_rounds=transfer_rounds,
        ledger_rounds=ledger_rounds, checkpoint_rounds=checkpoint_rounds,
    )
    model = bounded_model_check_v5(max_depth=17)

    identity = build_android_artifact_identity_v1(
        source_fingerprint="1" * 64, build_payload_sha256="2" * 64,
        build_manifest_sha256="3" * 64, toolchain_lock_sha256="4" * 64,
        version_code=10,
    )
    inputs = qualify_android_build_inputs_v1(_synthetic_lock(), _synthetic_manifest(), expected_payload_sha256="5" * 64)
    receipt = {"status": "DEBUG_APK_BUILT", "apk_sha256": "6" * 64, "input_identity_sha256": identity["identity_sha256"]}
    dual_build = compare_debug_build_receipts_v1(receipt, dict(receipt))
    mismatch = dict(receipt); mismatch["apk_sha256"] = "7" * 64
    dual_build_mismatch_rejected = not compare_debug_build_receipts_v1(receipt, mismatch)["ok"]

    pending_runtime = qualify_runtime_dossier_v2({}, {}, expected_apk_sha256="6" * 64)
    runtime_overclaim_rejected = not pending_runtime["ok"]

    candidate = "8" * 64
    bundle = build_windows_campaign_bundle_v1({
        "candidate_sha256": candidate,
        "campaign_checkpoint_sha256": "9" * 64,
        "preflight_bundle_sha256": "a" * 64,
        "campaign_plan_template_sha256": "b" * 64,
        "fault_matrix_sha256": "c" * 64,
        "recovery_proof_sha256": "d" * 64,
    })
    blank = blank_physical_evidence_set_v1(candidate)
    resume_ok = 0
    rounds = max(1, int(resume_rounds))
    for _ in range(rounds):
        verdict = qualify_campaign_resume_v2(candidate_sha256=candidate, evidence=blank, expected_candidate_sha256=candidate)
        if verdict["ok"] and verdict["next_gate"] == PHYSICAL_GATES[0]:
            resume_ok += 1
    skipped = [dict(x) for x in blank]
    skipped[1].update({"status": "PASS", "source": "physical_windows", "observed_at": "2026-09-17T00:00:00Z"})
    skip_rejected = not qualify_campaign_resume_v2(candidate_sha256=candidate, evidence=skipped, expected_candidate_sha256=candidate)["ok"]
    identity_mismatch_rejected = not qualify_campaign_resume_v2(candidate_sha256="f" * 64, evidence=blank, expected_candidate_sha256=candidate)["ok"]

    authority_safe = qualify_authority_boundary_v2(["run_tests", "terminal_bounded", "collect_evidence", "build_debug_artifact"])
    authority_unsafe = qualify_authority_boundary_v2(["run_tests", "automatic_installation", "payments"])

    ok = bool(
        base["ok"] and model["ok"] and identity["ok"] and inputs["ok"] and dual_build["ok"]
        and dual_build_mismatch_rejected and runtime_overclaim_rejected and bundle["ok"]
        and resume_ok == rounds and skip_rejected and identity_mismatch_rejected
        and authority_safe["ok"] and not authority_unsafe["ok"]
    )
    return {
        "ok": ok,
        "base_soak_guard_v6": base,
        "model_checker_v5": model,
        "android_artifact_identity": identity,
        "android_build_inputs": inputs,
        "synthetic_dual_build_contract": dual_build,
        "dual_build_mismatch_rejected": dual_build_mismatch_rejected,
        "runtime_overclaim_rejected": runtime_overclaim_rejected,
        "campaign_bundle": bundle,
        "resume_rounds": rounds,
        "resume_verified": resume_ok,
        "skip_rejected": skip_rejected,
        "candidate_identity_mismatch_rejected": identity_mismatch_rejected,
        "authority_safe": authority_safe,
        "authority_forbidden_rejected": not authority_unsafe["ok"],
        "automatic_publication": False,
        "automatic_installation": False,
    }
