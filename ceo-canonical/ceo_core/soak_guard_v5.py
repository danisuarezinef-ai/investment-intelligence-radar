from __future__ import annotations

import os
from typing import Any

from .android_evidence_import_v1 import validate_android_evidence_import_v1
from .cross_platform_parity_v1 import evaluate_cross_platform_parity_v1
from .mobile_sync_v4 import MobileSyncV4
from .update_failure_lab_v3 import UpdateFailureLabV3
from .update_model_checker_v3 import bounded_model_check_v3
from .update_transaction_ledger_v2 import UpdateTransactionLedgerV2


def _platform_fixture(ui: str, package: str) -> dict[str, Any]:
    return {
        "shared_core_protocol": 2,
        "schemas": {"task": 1, "evidence": 3, "mobile_sync": 4, "update_metadata": 2},
        "capabilities": ["task_exchange", "evidence_exchange", "update_metadata", "capability_manifest"],
        "ui_surface": ui,
        "package_kind": package,
    }


def run_soak_guard_v5(*, seeds: int = 1800, steps: int = 220, transfer_rounds: int = 5000, ledger_rounds: int = 2000) -> dict[str, Any]:
    lab = UpdateFailureLabV3.campaign(seeds=seeds, steps=steps)
    model = bounded_model_check_v3(max_depth=17)

    key = os.urandom(32)
    accepted = 0
    for n in range(max(1, int(transfer_rounds))):
        sender = MobileSyncV4(key)
        receiver = MobileSyncV4(key)
        envs = sender.issue_transfer([
            {"kind": "status", "payload": {"n": n}},
            {"kind": "test_result", "payload": {"ok": True}},
        ], chunk_size=1)
        verdict = receiver.verify_transfer(envs)
        if verdict["side_effects_allowed"] is False and len(verdict["items"]) == 2:
            accepted += 1

    ledger = UpdateTransactionLedgerV2(max_records=max(1, int(ledger_rounds)))
    kinds = ("candidate_seen", "preflight_started", "preflight_passed", "snapshot_recorded")
    for n in range(max(1, int(ledger_rounds))):
        ledger.append(kinds[n % len(kinds)], {"round": n, "authority": []})
    ledger_result = ledger.verify()

    parity = evaluate_cross_platform_parity_v1(
        _platform_fixture("windows_desktop", "windows_zip"),
        _platform_fixture("android_native", "android_apk"),
    )
    android = validate_android_evidence_import_v1({
        "status": "RUNTIME_HARDENING_HARNESS_READY",
        "source_fingerprint": "1" * 64,
        "sbom_sha256": "2" * 64,
        "build_payload_sha256": "3" * 64,
        "checkpoint_sha256": "4" * 64,
        "source_tests_passed": 194,
        "source_tests_failed": 0,
        "runtime_api35_executed": False,
        "runtime_api36_executed": False,
        "android_runtime_accepted": False,
        "production_verified": False,
    })
    rounds = max(1, int(transfer_rounds))
    ok = bool(lab["ok"] and model["ok"] and accepted == rounds and ledger_result["ok"] and parity["ok"] and android["ok"])
    return {
        "ok": ok,
        "failure_lab": lab,
        "model_checker_v3": model,
        "transfer_rounds": rounds,
        "transfers_accepted": accepted,
        "ledger": ledger_result,
        "parity": parity,
        "android_source_evidence": android,
        "automatic_publication": False,
        "automatic_installation": False,
    }
