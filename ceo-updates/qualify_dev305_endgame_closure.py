from __future__ import annotations

import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path("/tmp/dev305")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.autonomous_loop import AutonomousProjectLoop
from ceo_core.useful_output_watchdog_v2 import UsefulOutputWatchdogV2
from ceo_core.productive_truth_v2 import ProductiveTruthV2
from ceo_core.scheduler import RELIABILITY_EPOCH, _apply_reliability_epoch_migration

EXPECTED_VERSION = "1.5.81-rc1-endgame-closure"
EXPECTED_EPOCH = "dev305-endgame-closure-v1"


def state99() -> ProjectState:
    s = ProjectState(goal="Gate operativo 1.5.80", power_percent=20)
    s.metadata["require_goal_audit"] = True
    s.metadata["goal_audit_passed"] = False
    for i in range(3):
        t = Task(
            title=f"productive-{i}",
            status=TaskStatus.COMPLETE,
            metadata={"task_role": "productive"},
        )
        s.tasks[t.id] = t
        s.root_task_ids.append(t.id)
    # Historical/current broken-cycle evidence is retained but rebaselined by epoch.
    s.metadata["worker_recoveries"] = 4
    s.metadata["reliability_epoch_v1"] = {"epoch": "dev304-provider-resilience-v1"}
    s.metadata["productive_truth_v2"] = {
        "epoch": "dev304-provider-resilience-v1",
        "productive_watermark": 3,
        "recoveries_at_watermark": 0,
        "stalled": True,
        "status": "stalled",
    }
    s.metadata["operator_productivity_state"] = "BLOQUEADO"
    return s


def test_99pct_creates_goal_audit_even_with_provider_wait() -> None:
    s = state99()
    report = _apply_reliability_epoch_migration(s)
    assert report["changed"] is True
    assert RELIABILITY_EPOCH == EXPECTED_EPOCH
    s.metadata["provider_wait_v1"] = {
        "active": True,
        "category": "quota",
        "provider": "gemini-interactions",
        "retry_after_seconds": 300,
        "retry_after_ts": time.time() + 300,
        "recoveries_consumed": 0,
    }

    loop = AutonomousProjectLoop()
    out = loop.ensure_progress(s)
    assert out["status"] == "goal_audit_created", out
    audits = [t for t in s.leaf_tasks if t.metadata.get("goal_continuity_audit")]
    assert len(audits) == 1
    assert audits[0].status == TaskStatus.READY
    print("DEV305_99PCT_AUDIT_CREATED_PASS")


def test_waiting_audit_does_not_churn_or_block() -> None:
    s = state99()
    _apply_reliability_epoch_migration(s)
    s.metadata["provider_wait_v1"] = {
        "active": True,
        "category": "quota",
        "provider": "gemini-interactions",
        "retry_after_seconds": 300,
        "retry_after_ts": time.time() + 300,
        "recoveries_consumed": 0,
    }
    audit = Task(
        title="Goal continuity audit #1: plan the next autonomous work batch",
        status=TaskStatus.BLOCKED,
        metadata={
            "goal_continuity_audit": True,
            "control_plane_atomic": True,
            "waiting_provider_v1": {
                "active": True,
                "category": "quota",
                "provider": "gemini-interactions",
                "retry_after_ts": time.time() + 300,
            },
            "retry_after_ts": time.time() + 300,
        },
    )
    s.tasks[audit.id] = audit
    s.root_task_ids.append(audit.id)

    before = int(s.metadata.get("worker_recoveries", 0) or 0)
    out = AutonomousProjectLoop().ensure_progress(s)
    after = int(s.metadata.get("worker_recoveries", 0) or 0)
    assert out["status"] == "waiting_provider", out
    assert before == after, (before, after)
    assert "autonomy_stalled" not in s.metadata

    truth = ProductiveTruthV2().assess(s)
    assert truth.status == "waiting_provider", truth
    assert truth.stalled is False, truth

    wd = UsefulOutputWatchdogV2().tick(s)
    assert wd.status == "ESPERANDO PROVEEDOR", wd
    assert wd.fuse_open is False, wd
    assert s.metadata["operator_productivity_state"] == "ESPERANDO PROVEEDOR"
    print("DEV305_WAITING_AUDIT_ZERO_CHURN_PASS")


def test_provider_wait_not_fallback_candidate() -> None:
    from ceo_core.productive_fallback_orchestrator_v1 import ProductiveFallbackOrchestratorV1
    s = ProjectState(goal="provider wait fallback guard")
    t = Task(
        title="Final provider-dependent audit",
        status=TaskStatus.BLOCKED,
        metadata={
            "task_role": "productive",
            "waiting_provider_v1": {"active": True, "category": "quota"},
        },
    )
    s.tasks[t.id] = t
    s.root_task_ids.append(t.id)
    out = ProductiveFallbackOrchestratorV1().apply(s)
    assert out.rebuilt == 0 and out.provider_deferred == 0, out
    assert t.status == TaskStatus.BLOCKED
    print("DEV305_PROVIDER_WAIT_FALLBACK_EXCLUSION_PASS")


def source_semantics() -> None:
    contract = json.loads((ROOT / "CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
    assert contract["app_version"] == EXPECTED_VERSION

    scheduler = (ROOT / "ceo_core" / "scheduler.py").read_text(encoding="utf-8")
    loop = (ROOT / "ceo_core" / "autonomous_loop.py").read_text(encoding="utf-8")
    watchdog = (ROOT / "ceo_core" / "useful_output_watchdog_v2.py").read_text(encoding="utf-8")
    fallback = (ROOT / "ceo_core" / "productive_fallback_orchestrator_v1.py").read_text(encoding="utf-8")
    ui = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")

    assert 'and not bool((self.state.metadata.get("provider_wait_v1") or {}).get("active"))' not in scheduler
    assert '"status": "waiting_provider"' in loop
    assert "ESPERANDO PROVEEDOR" in watchdog
    assert "not t.metadata.get('waiting_provider_v1')" in fallback
    assert "operator_block_reason" in ui
    assert f'RELIABILITY_EPOCH = "{EXPECTED_EPOCH}"' in scheduler
    print("DEV305_SOURCE_SEMANTICS_PASS")


def main() -> None:
    test_99pct_creates_goal_audit_even_with_provider_wait()
    test_waiting_audit_does_not_churn_or_block()
    test_provider_wait_not_fallback_candidate()
    source_semantics()
    print("DEV305_ENDGAME_CLOSURE_QUALIFICATION_PASS")


if __name__ == "__main__":
    main()
