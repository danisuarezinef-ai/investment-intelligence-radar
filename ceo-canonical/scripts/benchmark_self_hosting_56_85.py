from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState
from ceo_core.self_hosting_field import (
    DesktopWatchdog, ChromeWatchdog, ProviderWatchdog, FieldEvidenceAuthority,
    FieldEvidenceItem, FieldGateAntiSpoofing, HumanAttentionQueue,
    TrustedApprovalBroker, UnifiedFieldEvidenceLedger, SelfHostingFieldOpsCore,
    EmergencyStopController, SafeResumeController,
)


def main() -> int:
    started = time.time()
    state = ProjectState(goal="benchmark field operations")
    with tempfile.TemporaryDirectory(prefix="ceo-field-bench-") as td:
        ledger = UnifiedFieldEvidenceLedger(FieldEvidenceAuthority(Path(td) / "field.key"))
        anti = FieldGateAntiSpoofing(ledger)
        valid = 0
        for i in range(250):
            run = ledger.begin(state, mission=f"valid-{i}", platform_name="windows")
            ledger.add(state, run["run_id"], FieldEvidenceItem(kind="proof", value="verified"))
            row = ledger.finalize(state, run["run_id"], success=True)
            valid += int(ledger.verify(row, require_windows=True)["verified"])
        tamper_blocked = 0
        for i in range(1000):
            run = ledger.begin(state, mission=f"tamper-{i}", platform_name="windows")
            ledger.add(state, run["run_id"], FieldEvidenceItem(kind="proof", value="verified"))
            row = ledger.finalize(state, run["run_id"], success=True)
            state.metadata[ledger.KEY][run["run_id"]]["items"][0]["value"] = f"tampered-{i}"
            tamper_blocked += int(not ledger.verify(state.metadata[ledger.KEY][run["run_id"]], require_windows=True)["verified"])
        source_spoof_blocked = 0
        for i in range(500):
            run = ledger.begin(state, mission=f"spoof-{i}", source="agent", platform_name="windows")
            ledger.add(state, run["run_id"], FieldEvidenceItem(kind="proof", value="verified"))
            ledger.finalize(state, run["run_id"], success=True)
            source_spoof_blocked += int(anti.best_verified(state, f"spoof-{i}", require_windows=True)["status"] == "NOT_VERIFIED")

        watchdog_cases = 0
        for i in range(5000):
            DesktopWatchdog().evaluate(last_progress_age_s=i % 200, window_present=i % 11 != 0, process_alive=i % 17 != 0)
            ChromeWatchdog().evaluate(browser_connected=i % 13 != 0, expected_url="https://a", current_url="https://a/x" if i % 19 else "https://b", session_authenticated=i % 23 != 0)
            ProviderWatchdog().evaluate(authenticated=i % 29 != 0, timeout_rate=(i % 5) / 10, rate_limited=i % 31 == 0, recent_success_rate=.95 if i % 7 else .7)
            watchdog_cases += 3

        queue = HumanAttentionQueue()
        for i in range(1000):
            queue.add(state, category="bench", summary=f"issue {i}", severity="critical" if i % 100 == 0 else "low", blocking=i % 100 == 0)
        attention_sorted = queue.open(state)
        attention_priority_ok = bool(attention_sorted and attention_sorted[0]["blocking"] and attention_sorted[0]["severity"] == "critical")

        approvals = TrustedApprovalBroker(FieldEvidenceAuthority(Path(td) / "approval.key"))
        approval_once_ok = 0
        for i in range(500):
            issued = approvals.issue_local(state, action=f"action-{i}", trusted_channel=True)
            approvals.consume(state, action=f"action-{i}", token=issued["token"])
            try:
                approvals.consume(state, action=f"action-{i}", token=issued["token"])
            except PermissionError:
                approval_once_ok += 1

        emergency_cycles = 0
        for i in range(500):
            EmergencyStopController().stop(state, reason=f"bench-{i}")
            SafeResumeController().resume(state, pending_actions=[], human_confirmed=False)
            emergency_cycles += 1

        clean_state = ProjectState(goal="field gate must remain closed")
        core = SelfHostingFieldOpsCore()
        pre = core.local_preflight(clean_state)
        missions = core.missions.all(clean_state)
        all_field_not_verified = all(x["status"] == "NOT_VERIFIED" for x in missions.values())
        certification = core.certification.assess(clean_state)

        report = {
            "version": "1.1.0-dev7",
            "status": "PASS" if all([
                valid == 250, tamper_blocked == 1000, source_spoof_blocked == 500,
                attention_priority_ok, approval_once_ok == 500, emergency_cycles == 500,
                pre["pass"], all_field_not_verified, not certification["ready"],
            ]) else "FAIL",
            "valid_signed_evidence": {"expected": 250, "verified": valid},
            "tamper_detection": {"attempts": 1000, "blocked": tamper_blocked},
            "source_spoofing": {"attempts": 500, "blocked": source_spoof_blocked},
            "watchdog_evaluations": watchdog_cases,
            "attention_queue": {"items": 1000, "priority_order_ok": attention_priority_ok},
            "trusted_approvals": {"issued": 500, "one_time_reuse_blocked": approval_once_ok},
            "emergency_stop_resume_cycles": emergency_cycles,
            "local_preflight_pass": pre["pass"],
            "field_missions_without_physical_run": {k: v["status"] for k, v in missions.items()},
            "all_field_not_verified_without_physical_run": all_field_not_verified,
            "certification_ready_without_field": certification["ready"],
            "production_verified": False,
            "elapsed_seconds": round(time.time() - started, 4),
        }
        out = ROOT / "SELF_HOSTING_56_85_BENCHMARK.json"
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
