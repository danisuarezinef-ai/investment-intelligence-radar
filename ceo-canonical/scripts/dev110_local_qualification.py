from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.android_contract_v2 import android_contract_v2, validate_android_request_v2
from ceo_core.benchmark_arbitrator_v1 import arbitrate_candidate_metrics
from ceo_core.convergence_gate_v1 import evaluate_convergence
from ceo_core.convergence_merge_plan_v1 import build_convergence_plan
from ceo_core.mobile_offload_planner_v1 import plan_mobile_offload
from ceo_core.mobile_sync_v3 import MobileSyncV3
from ceo_core.release_readiness_v8 import qualify_release_v8
from ceo_core.self_dev_receipt_v2 import validate_self_development_receipt_v2
from ceo_core.soak_guard_v3 import run_soak_guard_v3
from ceo_core.update_model_checker_v1 import bounded_model_check


def receipt(cid: str, changed: dict[str, str], *, base: str = "1.3.77-rc1-mobile-reliability-v3") -> dict:
    return {
        "candidate_id": cid,
        "base_version": base,
        "candidate_version": cid + "-candidate",
        "changed_files": sorted(changed),
        "file_hashes": changed,
        "tests": {"passed": 50, "failed": 0},
        "published": False, "installed": False, "auto_promoted": False,
        "evidence_refs": [cid + ":tests"],
        "safety": {
            "stable_unchanged": True,
            "automatic_spending_false": True,
            "automatic_publication_false": True,
            "automatic_installation_false": True,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--soak-seeds", type=int, default=1000)
    ap.add_argument("--soak-steps", type=int, default=200)
    ap.add_argument("--sync-rounds", type=int, default=5000)
    ns = ap.parse_args()

    h1 = "1" * 64; h2 = "2" * 64; h3 = "3" * 64
    windows = receipt("windows-self-dev-101", {"ceo_core/quality_gate.py": h1, "ceo_core/scheduler.py": h2})
    mobile = receipt("mobile-dev110", {"ceo_core/executive_snapshot_v2.py": h3, "ceo_core/scheduler.py": h2})
    out: dict[str, object] = {}
    out["receipt_v2"] = {
        "windows": validate_self_development_receipt_v2(windows, expected_base_version=windows["base_version"]),
        "mobile": validate_self_development_receipt_v2(mobile, expected_base_version=mobile["base_version"]),
    }
    out["convergence_plan"] = build_convergence_plan(windows, mobile, common_base_version=windows["base_version"])
    baseline = {"quality": [0.80, 0.81, 0.79], "latency": [100, 98, 102]}
    wm = {"quality": [0.83, 0.82, 0.84], "latency": [99, 98, 100]}
    mm = {"quality": [0.85, 0.84, 0.86], "latency": [97, 96, 98]}
    directions = {"quality": "higher", "latency": "lower"}
    out["benchmark"] = arbitrate_candidate_metrics(baseline, wm, mm, directions)
    out["model_checker"] = bounded_model_check(max_depth=14)

    key = os.urandom(32)
    sender = MobileSyncV3(key); receiver = MobileSyncV3(key)
    env = sender.issue_batch([
        {"kind": "status", "payload": {"state": "working"}},
        {"kind": "development_receipt", "payload": {"candidate_id": "windows-self-dev-101"}},
    ])
    v = receiver.verify_batch(env, expected_sequence=1, expected_previous_transcript="0" * 64)
    replay_rejected = False
    try:
        receiver.verify_batch(env, expected_sequence=1, expected_previous_transcript="0" * 64)
    except PermissionError:
        replay_rejected = True
    out["mobile_sync_v3"] = {"verified": len(v["items"]) == 2, "replay_rejected": replay_rejected}

    out["mobile_offload"] = plan_mobile_offload([
        {"id": "a", "kind": "summarize", "estimated_ram_gb": 2},
        {"id": "b", "kind": "code_review", "estimated_ram_gb": 4},
        {"id": "c", "kind": "publication", "estimated_ram_gb": 1},
    ], {"ram_total_gb": 24, "ram_free_gb": 18, "battery_percent": 75, "charging": False, "thermal": "normal"})

    contract = android_contract_v2()
    out["android_contract_v2"] = {
        "contract": contract,
        "install_without_confirmation": validate_android_request_v2("in_app_update_install", explicit_install_confirmation=False),
        "install_with_confirmation": validate_android_request_v2("in_app_update_install", explicit_install_confirmation=True),
    }
    out["convergence_gate"] = evaluate_convergence(
        windows, mobile, common_base_version=windows["base_version"],
        baseline_metrics=baseline, windows_metrics=wm, mobile_metrics=mm, directions=directions,
    )
    out["soak_guard_v3"] = run_soak_guard_v3(seeds=ns.soak_seeds, steps=ns.soak_steps, sync_rounds=ns.sync_rounds)

    gates = {
        "dev100_ready": True,
        "receipt_v2": bool(out["receipt_v2"]["windows"]["ok"] and out["receipt_v2"]["mobile"]["ok"]),
        "convergence_plan": bool(out["convergence_plan"]["same_result_overlap"] == ["ceo_core/scheduler.py"] and out["convergence_plan"]["automatic_merge"] is False),
        "benchmark_arbitrator": bool(out["benchmark"]["benchmark_preferred_candidate"] == "mobile" and out["benchmark"]["automatic_promotion"] is False),
        "model_checker": bool(out["model_checker"]["ok"]),
        "mobile_sync_v3": bool(out["mobile_sync_v3"]["verified"] and out["mobile_sync_v3"]["replay_rejected"]),
        "mobile_offload_planner": bool(len(out["mobile_offload"]["admitted"]) == 2 and len(out["mobile_offload"]["deferred"]) == 1 and out["mobile_offload"]["publication_allowed"] is False),
        "android_contract_v2": bool(contract["single_public_install_package"] and contract["manual_post_install_configuration_required"] is False and out["android_contract_v2"]["install_without_confirmation"]["allowed"] is False),
        "convergence_gate": bool(out["convergence_gate"]["automatic_merge"] is False and out["convergence_gate"]["automatic_publication"] is False),
        "soak_guard_v3": bool(out["soak_guard_v3"]["ok"]),
    }
    out["readiness"] = qualify_release_v8(gates, windows_physical_verified=False, human_release_authorized=False)
    out["ok"] = bool(out["readiness"]["local_candidate_ready"] and not out["readiness"]["production_ready"] and out["readiness"]["windows_update_freeze_respected"])

    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.json:
        Path(ns.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if out["ok"] else 7

if __name__ == "__main__":
    raise SystemExit(main())
