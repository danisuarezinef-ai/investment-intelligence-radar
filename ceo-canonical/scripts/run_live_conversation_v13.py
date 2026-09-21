from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from ceo_core.models import ProjectState, Task
from ceo_core.provider_factory import build_providers
from ceo_core.resource_governor import ResourceGovernor
from ceo_core.routing import MultiProviderRouter
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.sqlite_store import SqliteCheckpointStore
from ceo_core.validation import StrictReleaseGates, ValidationEvidence, ValidationRegistry


def require_windows() -> None:
    if os.name != "nt":
        raise SystemExit("This validation must run on the target Windows PC.")


def registry_for(outdir: Path) -> ValidationRegistry:
    path = outdir / "validation_registry_physical.json"
    if not path.exists():
        baseline = Path(__file__).resolve().parents[1] / "reports" / "VALIDATION_REGISTRY_MVP_0.8.json"
        if baseline.exists():
            shutil.copy2(baseline, path)
    return ValidationRegistry(path)


async def main() -> int:
    require_windows()
    root = Path(__file__).resolve().parents[1]
    outdir = Path(os.getenv("CEO_VALIDATION_OUT") or (Path.home() / "Desktop" / "CEO_VALIDATION_RESULTS")).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    data_root = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "CEO de IAs"
    data_root.mkdir(parents=True, exist_ok=True)

    providers = build_providers(root, data_root)
    real = [p for p in providers if p.name != "mock"]
    if not real:
        report = {
            "passed": False,
            "error": "No real provider configured. Use OPENAI_API_KEY/GEMINI_API_KEY or the browser-login path in VALIDAR_CONVERSACION_REAL_V13.cmd.",
        }
        (outdir / "LIVE_CONVERSATION_V13.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    state = ProjectState(
        goal="CEO live autonomous conversation validation",
        goal_definition="Complete one real AI work unit using at least two turns without the human typing continue.",
        completion_criteria=["At least two turns", "Final marker CEO_LIVE_VALIDATED", "Zero required human continue prompts"],
        power_percent=20,
        verification_percent=0,
        notifications_enabled=False,
    )
    task = Task(
        title="Real two-turn autonomous conversation",
        description=(
            "This is a validation run. On TURN 1, briefly analyze the task and deliberately leave one small validation step "
            "for the same conversation; end with CEO_RESULT status=continue and a concrete next_instruction. "
            "Do NOT emit CEO_LIVE_VALIDATED on turn 1. On TURN 2, complete the validation, include the exact marker "
            "CEO_LIVE_VALIDATED in the substantive response, and end with CEO_RESULT status=complete."
        ),
        acceptance_criteria=[
            "At least two conversation turns in the same provider conversation",
            "Final substantive response contains CEO_LIVE_VALIDATED",
            "No human continue prompt is required",
        ],
        estimated_seconds=8,
    )
    state.tasks[task.id] = task
    state.root_task_ids = [task.id]

    db = outdir / "live_conversation_v13.db"
    store = SqliteCheckpointStore(db)
    sched = ContinuousScheduler(
        state,
        None,
        store,
        router=MultiProviderRouter(real),
        governor=ResourceGovernor(hard_worker_cap=1),
    )
    started = time.perf_counter()
    sched.start()
    deadline = time.monotonic() + 600
    try:
        while not state.completed_at and time.monotonic() < deadline:
            if task.status.value in {"failed", "needs_review"}:
                break
            await asyncio.sleep(0.25)
    finally:
        await sched.stop()

    result_text = task.result or ""
    passed = bool(
        state.completed_at
        and task.conversation_turns >= 2
        and "CEO_LIVE_VALIDATED" in result_text
        and state.human_interventions_required == 0
    )
    report = {
        "passed": passed,
        "provider": task.provider_name,
        "turns": task.conversation_turns,
        "conversation_id_present": bool(task.conversation_id),
        "human_interventions_required": state.human_interventions_required,
        "human_interventions_avoided": state.human_interventions_avoided,
        "task_status": task.status.value,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "final_marker_present": "CEO_LIVE_VALIDATED" in result_text,
        "result_excerpt": result_text[-1800:],
        "task_metadata": {k: v for k, v in task.metadata.items() if k not in {"context"}},
    }

    registry = registry_for(outdir)
    evidence = ValidationEvidence(
        evidence_id="windows-v13-live-conversation",
        kind="live",
        environment="windows-live-provider",
        passed=passed,
        detail=json.dumps(report, ensure_ascii=False, default=str),
    )
    registry.record("conversation_controller", evidence)
    registry.record("live_ai_provider_validation", ValidationEvidence(
        evidence_id="windows-v13-live-provider",
        kind="live",
        environment="windows-live-provider",
        passed=passed,
        detail=json.dumps(report, ensure_ascii=False, default=str),
    ))
    # A passing live run is also direct live evidence for the scheduler; it does not erase prior evidence.
    registry.record("scheduler", ValidationEvidence(
        evidence_id="windows-v13-live-scheduler",
        kind="live",
        environment="windows-live-provider",
        passed=passed,
        detail=json.dumps(report, ensure_ascii=False, default=str),
    ))
    if task.provider_name and "browser" in task.provider_name.lower():
        registry.record("browser_worker", ValidationEvidence(
            evidence_id="windows-v13-live-browser-chat",
            kind="live",
            environment="windows-live-provider",
            passed=passed,
            detail=json.dumps(report, ensure_ascii=False, default=str),
        ))

    gates = StrictReleaseGates().assess(registry)
    report["release_gates"] = gates
    report["maturity_summary"] = registry.summary()
    report["critical_maturity"] = {
        c: registry.records[c].maturity if c in registry.records else "MISSING"
        for c in StrictReleaseGates.CRITICAL
    }
    (outdir / "LIVE_CONVERSATION_V13.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    summary = [
        "CEO de IAs - Live Conversation Validation v13",
        f"Live conversation: {'PASS' if passed else 'FAIL'}",
        f"Provider: {task.provider_name}",
        f"Turns: {task.conversation_turns}",
        f"Human continue prompts required: {state.human_interventions_required}",
        f"Autonomous interventions avoided: {state.human_interventions_avoided}",
        f"Final marker present: {'YES' if 'CEO_LIVE_VALIDATED' in result_text else 'NO'}",
        f"Conversation Controller maturity: {report['critical_maturity'].get('conversation_controller')}",
        f"Scheduler maturity: {report['critical_maturity'].get('scheduler')}",
        f"Persistence maturity: {report['critical_maturity'].get('persistence_recovery')}",
        f"Resource Governor maturity: {report['critical_maturity'].get('resource_governor')}",
        f"Browser Worker maturity: {report['critical_maturity'].get('browser_worker')}",
        f"Release channel: {gates.get('highest_channel')}",
    ]
    (outdir / "VALIDATION_SUMMARY_V13.txt").write_text("\n".join(summary), encoding="utf-8")
    print("\n".join(summary))
    print(f"\nDetailed report: {outdir / 'LIVE_CONVERSATION_V13.json'}")
    print(f"Registry: {outdir / 'validation_registry_physical.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
