from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import traceback
import sys
from pathlib import Path

# When Python executes a file under scripts\, sys.path[0] is that folder rather than
# the project root. Add the root explicitly so local ceo_core imports are reliable
# even when the editable package is not installed in site-packages.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState, Task
from ceo_core.provider_factory import build_providers
from ceo_core.resource_governor import ResourceGovernor
from ceo_core.routing import MultiProviderRouter
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.sqlite_store import SqliteCheckpointStore
from ceo_core.validation import StrictReleaseGates, ValidationEvidence, ValidationRegistry


def require_windows() -> None:
    if os.name != "nt":
        raise RuntimeError("This validation must run on the target Windows PC.")


def outdir() -> Path:
    p = Path(os.getenv("CEO_VALIDATION_OUT") or (Path.home() / "Desktop" / "CEO_VALIDATION_RESULTS")).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def registry_for(path: Path) -> ValidationRegistry:
    registry_path = path / "validation_registry_physical.json"
    if not registry_path.exists():
        baseline = Path(__file__).resolve().parents[1] / "reports" / "VALIDATION_REGISTRY_MVP_0.8.json"
        if baseline.exists():
            shutil.copy2(baseline, registry_path)
    return ValidationRegistry(registry_path)


def write_failure(path: Path, stage: str, exc: BaseException) -> int:
    detail = {
        "passed": False,
        "stage": stage,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }
    (path / "LIVE_CONVERSATION_V16.json").write_text(json.dumps(detail, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = [
        "CEO de IAs - Live Conversation Validation v16",
        "Live conversation: FAIL/PARTIAL",
        f"Stage: {stage}",
        f"Error: {type(exc).__name__}: {exc}",
        "Conversation Controller maturity: NOT PROMOTED",
        "Release channel: unchanged",
        "See LIVE_CONVERSATION_V16.json and V16_console.log for details.",
    ]
    (path / "VALIDATION_SUMMARY_V16.txt").write_text("\n".join(summary), encoding="utf-8")
    print("\n".join(summary))
    return 1


def detect_browser() -> str | None:
    if os.getenv("CEO_CHROMIUM_EXECUTABLE") and Path(os.environ["CEO_CHROMIUM_EXECUTABLE"]).is_file():
        return os.environ["CEO_CHROMIUM_EXECUTABLE"]
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    pfx86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    candidates = [
        pf / "Google" / "Chrome" / "Application" / "chrome.exe",
        pfx86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        local / "Google" / "Chrome" / "Application" / "chrome.exe",
        pf / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        pfx86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        local / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    found = next((p for p in candidates if p.is_file()), None)
    return str(found) if found else None


async def live_run(path: Path) -> int:
    require_windows()
    root = Path(__file__).resolve().parents[1]
    data_root = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "CEO de IAs"
    data_root.mkdir(parents=True, exist_ok=True)

    if os.getenv("CEO_BROWSER_START_URL"):
        browser = detect_browser()
        if browser:
            os.environ["CEO_CHROMIUM_EXECUTABLE"] = browser
        (path / "V16_browser_detected.txt").write_text(browser or "NOT FOUND", encoding="utf-8")

    print("[V16] Building real providers...")
    providers = build_providers(root, data_root)
    real = [p for p in providers if p.name != "mock"]
    if not real:
        raise RuntimeError("No real provider configured after authentication/API detection.")
    print("[V16] Providers: " + ", ".join(f"{p.name}/{getattr(p.kind, 'value', p.kind)}" for p in real))

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

    db = path / "live_conversation_v16.db"
    if db.exists():
        try:
            db.unlink()
        except OSError:
            pass
    store = SqliteCheckpointStore(db)
    sched = ContinuousScheduler(state, None, store, router=MultiProviderRouter(real), governor=ResourceGovernor(hard_worker_cap=1))
    started = time.perf_counter()
    print("[V16] Starting scheduler...")
    sched.start()
    deadline = time.monotonic() + 480
    last_turns = -1
    try:
        while not state.completed_at and time.monotonic() < deadline:
            if task.conversation_turns != last_turns:
                last_turns = task.conversation_turns
                print(f"[V16] turns={last_turns} status={task.status.value} provider={task.provider_name}")
            if task.status.value in {"failed", "needs_review"}:
                break
            await asyncio.sleep(0.5)
    finally:
        await sched.stop()

    result_text = task.result or ""
    timed_out = not state.completed_at and time.monotonic() >= deadline
    passed = bool(state.completed_at and task.conversation_turns >= 2 and "CEO_LIVE_VALIDATED" in result_text and state.human_interventions_required == 0)
    report = {
        "passed": passed,
        "timed_out": timed_out,
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

    registry = registry_for(path)
    evidence = ValidationEvidence(evidence_id="windows-v16-live-conversation", kind="live", environment="windows-live-provider", passed=passed, detail=json.dumps(report, ensure_ascii=False, default=str))
    registry.record("conversation_controller", evidence)
    registry.record("live_ai_provider_validation", ValidationEvidence(evidence_id="windows-v16-live-provider", kind="live", environment="windows-live-provider", passed=passed, detail=json.dumps(report, ensure_ascii=False, default=str)))
    registry.record("scheduler", ValidationEvidence(evidence_id="windows-v16-live-scheduler", kind="live", environment="windows-live-provider", passed=passed, detail=json.dumps(report, ensure_ascii=False, default=str)))
    if task.provider_name and "browser" in task.provider_name.lower():
        registry.record("browser_worker", ValidationEvidence(evidence_id="windows-v16-live-browser-chat", kind="live", environment="windows-live-provider", passed=passed, detail=json.dumps(report, ensure_ascii=False, default=str)))

    gates = StrictReleaseGates().assess(registry)
    report["release_gates"] = gates
    report["maturity_summary"] = registry.summary()
    report["critical_maturity"] = {c: registry.records[c].maturity if c in registry.records else "MISSING" for c in StrictReleaseGates.CRITICAL}
    (path / "LIVE_CONVERSATION_V16.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    summary = [
        "CEO de IAs - Live Conversation Validation v16",
        f"Live conversation: {'PASS' if passed else 'FAIL/PARTIAL'}",
        f"Provider: {task.provider_name}",
        f"Turns: {task.conversation_turns}",
        f"Task status: {task.status.value}",
        f"Timed out: {'YES' if timed_out else 'NO'}",
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
    (path / "VALIDATION_SUMMARY_V16.txt").write_text("\n".join(summary), encoding="utf-8")
    print("\n".join(summary))
    return 0 if passed else 1


async def main() -> int:
    path = outdir()
    (path / "V16_PYTHON_STARTED.txt").write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    try:
        return await live_run(path)
    except BaseException as exc:
        return write_failure(path, "live_run", exc)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
