from __future__ import annotations

import os
from typing import Any

from .android_build_readiness_v1 import qualify_android_build_readiness_v1
from .campaign_checkpoint_v1 import build_campaign_checkpoint_v1, verify_campaign_checkpoint_v1
from .capability_drift_guard_v1 import compare_capability_manifests_v1
from .physical_evidence_schema_v1 import blank_physical_evidence_set_v1
from .recovery_proof_v1 import bounded_recovery_proof_v1
from .update_failure_lab_v3 import UpdateFailureLabV3
from .update_fault_matrix_v1 import build_update_fault_matrix_v1
from .update_model_checker_v4 import bounded_model_check_v4
from .mobile_sync_v4 import MobileSyncV4
from .update_transaction_ledger_v2 import UpdateTransactionLedgerV2


def run_soak_guard_v6(*, seeds: int = 1800, steps: int = 220, transfer_rounds: int = 5000, ledger_rounds: int = 2000,
                      checkpoint_rounds: int = 3000) -> dict[str, Any]:
    lab = UpdateFailureLabV3.campaign(seeds=seeds, steps=steps)
    model = bounded_model_check_v4(max_depth=16)
    key = os.urandom(32)
    accepted = 0
    for n in range(max(1, int(transfer_rounds))):
        sender, receiver = MobileSyncV4(key), MobileSyncV4(key)
        envs = sender.issue_transfer([{"kind": "status", "payload": {"n": n}}, {"kind": "test_result", "payload": {"ok": True}}], chunk_size=1)
        verdict = receiver.verify_transfer(envs)
        if verdict["side_effects_allowed"] is False and len(verdict["items"]) == 2: accepted += 1
    ledger = UpdateTransactionLedgerV2(max_records=max(1, int(ledger_rounds)))
    kinds = ("candidate_seen", "preflight_started", "preflight_passed", "snapshot_recorded")
    for n in range(max(1, int(ledger_rounds))): ledger.append(kinds[n % len(kinds)], {"round": n, "authority": []})
    ledger_result = ledger.verify()
    candidate = "a" * 64
    checkpoint_ok = 0
    for n in range(max(1, int(checkpoint_rounds))):
        cp = build_campaign_checkpoint_v1(campaign_id=f"soak-{n}", candidate_sha256=candidate, evidence=blank_physical_evidence_set_v1(candidate))
        if cp["ok"] and verify_campaign_checkpoint_v1(cp)["ok"]: checkpoint_ok += 1
    drift_safe = compare_capability_manifests_v1(["task_exchange"], ["task_exchange", "evidence_exchange"])
    drift_unsafe = compare_capability_manifests_v1(["task_exchange"], ["task_exchange", "auto_install"])
    faults = build_update_fault_matrix_v1()
    recovery = bounded_recovery_proof_v1()
    android = qualify_android_build_readiness_v1({
        "status": "RUNTIME_HARDENING_HARNESS_READY", "source_fingerprint": "1"*64, "sbom_sha256": "2"*64,
        "build_payload_sha256": "3"*64, "checkpoint_sha256": "4"*64, "source_tests_passed": 194,
        "source_tests_failed": 0, "runtime_api35_executed": False, "runtime_api36_executed": False,
        "android_runtime_accepted": False, "production_verified": False,
    })
    rounds = max(1, int(transfer_rounds)); cps = max(1, int(checkpoint_rounds))
    ok = bool(lab["ok"] and model["ok"] and accepted == rounds and ledger_result["ok"] and checkpoint_ok == cps and drift_safe["ok"] and not drift_unsafe["ok"] and faults["ok"] and recovery["ok"] and android["ok"])
    return {
        "ok": ok, "failure_lab": lab, "model_checker_v4": model, "transfer_rounds": rounds, "transfers_accepted": accepted,
        "ledger": ledger_result, "checkpoint_rounds": cps, "checkpoints_verified": checkpoint_ok, "drift_safe": drift_safe,
        "drift_unsafe_rejected": not drift_unsafe["ok"], "fault_matrix": faults, "recovery_proof": recovery,
        "android_build_readiness": android, "automatic_publication": False, "automatic_installation": False,
    }
