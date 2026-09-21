from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]

from ceo_core.browser_worker import BrowserChatConfig, BrowserChatTransport
from ceo_core.credentials import WindowsCredentialManagerStore, WindowsDPAPISecretStore
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.providers.mock import MockWorkerProvider
from ceo_core.resource_adaptive import CapacityProfiler, GPUProbe
from ceo_core.resource_governor import ResourceGovernor
from ceo_core.sqlite_store import SqliteCheckpointStore
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.validation import StrictReleaseGates, ValidationEvidence, ValidationRegistry
from ceo_core.validation_harness import destructive_persistence_validation, idempotency_validation


def require_windows() -> None:
    if os.name != "nt":
        raise SystemExit("This physical validation must run on the target Windows PC.")


def find_browser() -> str | None:
    explicit = os.getenv("CEO_CHROMIUM_EXECUTABLE")
    if explicit and Path(explicit).exists():
        return explicit
    for name in ("msedge", "chrome", "chromium"):
        p = shutil.which(name)
        if p:
            return p
    roots = [os.getenv("PROGRAMFILES(X86)"), os.getenv("PROGRAMFILES"), os.getenv("LOCALAPPDATA")]
    suffixes = [
        Path("Microsoft/Edge/Application/msedge.exe"),
        Path("Google/Chrome/Application/chrome.exe"),
    ]
    for root in roots:
        if not root:
            continue
        for suffix in suffixes:
            candidate = Path(root) / suffix
            if candidate.exists():
                return str(candidate)
    return None


def api_alive(url: str = "http://127.0.0.1:8765/api/state") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return int(getattr(response, "status", 0)) == 200
    except Exception:
        return False


def installed_exe_candidates() -> list[Path]:
    local = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return [
        local / "Programs" / "CEO de IAs" / "CEO-de-IAs.exe",
        Path.home() / "Desktop" / "CEO-de-IAs.exe",
    ]


def ensure_installed_app() -> dict:
    if api_alive():
        return {"passed": True, "started_by_validator": False, "detail": "API already responding on 127.0.0.1:8765"}
    exe = next((p for p in installed_exe_candidates() if p.exists()), None)
    if not exe:
        return {"passed": False, "started_by_validator": False, "detail": "Installed CEO-de-IAs.exe not found in expected locations"}
    env = os.environ.copy()
    env["CEO_NO_AUTO_OPEN"] = "1"
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        subprocess.Popen([str(exe)], env=env, creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        return {"passed": False, "started_by_validator": False, "detail": f"Could not start installed EXE: {type(exc).__name__}: {exc}"}
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if api_alive():
            return {"passed": True, "started_by_validator": True, "detail": f"Installed EXE started and API responded: {exe}", "exe": str(exe)}
        time.sleep(0.5)
    return {"passed": False, "started_by_validator": True, "detail": f"EXE started but API did not respond within 30 s: {exe}", "exe": str(exe)}


async def browser_health() -> dict:
    exe = find_browser()
    if not exe:
        return {"passed": False, "detail": "Edge/Chrome/Chromium executable not found", "executable": None}
    with tempfile.TemporaryDirectory() as td:
        cfg = BrowserChatConfig(
            name="windows-physical-browser-v11",
            start_url="about:blank",
            input_selector="#x",
            send_selector="#s",
            assistant_selector="#a",
            profile_dir=str(Path(td) / "profile"),
            registry_path=str(Path(td) / "reg.json"),
            executable_path=exe,
            headless=True,
        )
        h = await BrowserChatTransport(cfg).healthcheck()
        return {"passed": bool(h.available), "detail": h.detail, "executable": exe}


async def scheduler_physical(outdir: Path) -> dict:
    db = outdir / "scheduler_physical.db"
    if db.exists():
        db.unlink()
    state = ProjectState(
        goal="Windows physical scheduler validation",
        goal_definition="Complete an isolated deterministic scheduler workload on the target Windows PC.",
        completion_criteria=["All diagnostic tasks complete"],
        power_percent=20,
        verification_percent=0,
        depth_percent=20,
        exploration_percent=0,
        notifications_enabled=False,
    )
    for i in range(30):
        task = Task(
            title=f"Physical diagnostic task {i+1}",
            description="Isolated deterministic validation work item.",
            status=TaskStatus.READY,
            estimated_seconds=0.12,
            acceptance_criteria=["Task completes successfully"],
        )
        state.tasks[task.id] = task
        state.root_task_ids.append(task.id)
    store = SqliteCheckpointStore(db)
    governor = ResourceGovernor(hard_worker_cap=4)
    sched = ContinuousScheduler(state, MockWorkerProvider(), store, governor=governor)
    started = time.perf_counter()
    sched.start()
    await asyncio.sleep(0.12)
    state.paused = True
    pause_seen = bool(state.paused)
    await asyncio.sleep(0.25)
    completed_during_pause = len(state.completed_leaf_tasks)
    state.power_percent = 70
    state.paused = False
    sched.start()
    deadline = time.monotonic() + 30
    while not state.completed_at and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    elapsed = time.perf_counter() - started
    completed = len(state.completed_leaf_tasks)
    if not state.completed_at:
        await sched.stop()
    store.save(state)
    loaded = store.load()
    reload_ok = bool(loaded and loaded.goal == state.goal and len(loaded.completed_leaf_tasks) == completed)
    integrity = store.integrity_check()
    passed = bool(state.completed_at and completed == 30 and reload_ok and integrity.get("ok") and pause_seen)
    return {
        "passed": passed,
        "tasks": 30,
        "completed": completed,
        "elapsed_seconds": round(elapsed, 3),
        "pause_seen": pause_seen,
        "completed_during_pause_window": completed_during_pause,
        "power_after_resume": state.power_percent,
        "sqlite_reload_ok": reload_ok,
        "sqlite_integrity": integrity,
    }


def load_baseline_registry(outdir: Path) -> ValidationRegistry:
    target = outdir / "validation_registry_physical.json"
    baseline = ROOT / "reports" / "VALIDATION_REGISTRY_MVP_0.8.json"
    if baseline.exists():
        shutil.copy2(baseline, target)
    return ValidationRegistry(target)


async def main() -> int:
    require_windows()
    outdir = Path(os.getenv("CEO_VALIDATION_OUT") or (Path.home() / "Desktop" / "CEO_VALIDATION_RESULTS")).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    registry = load_baseline_registry(outdir)

    app_launch = ensure_installed_app()

    governor = ResourceGovernor()
    profiler = CapacityProfiler(governor)
    probe_state = ProjectState(goal="Windows physical resource validation")
    cap = profiler.profile(probe_state)
    capacity = cap.__dict__ if hasattr(cap, "__dict__") else {k: getattr(cap, k) for k in cap.__slots__}
    resource = {
        "snapshot": governor.snapshot(),
        "scenarios": {str(p): governor.limits(p) for p in (20, 50, 80, 95)},
        "capacity": capacity,
        "gpu": GPUProbe().snapshot(),
    }
    resource_pass = bool(resource["snapshot"] and resource["scenarios"])
    registry.record("resource_governor", ValidationEvidence("windows-v11-resource", "physical", "windows-target", resource_pass, json.dumps(resource, default=str)))

    key = f"physical-v11-{int(time.time())}"
    secret = f"CEO-PHYSICAL-{int(time.time())}"
    dp = WindowsDPAPISecretStore()
    dp.put(key, secret)
    dp_ok = dp.get(key) == secret
    dp.delete(key)
    cm = WindowsCredentialManagerStore(namespace="CEO-de-IAs-Physical-V11")
    cm.put(key, secret)
    cm_ok = cm.get(key) == secret
    cm.delete(key)
    credentials = {"dpapi_roundtrip": dp_ok, "credential_manager_roundtrip": cm_ok}
    registry.record("credential_storage", ValidationEvidence("windows-v11-credentials", "physical", "windows-target", dp_ok and cm_ok, json.dumps(credentials)))

    browser = await browser_health()
    registry.record("browser_worker", ValidationEvidence("windows-v11-browser", "physical", "windows-target", bool(browser["passed"]), json.dumps(browser)))

    ram_gb = psutil.virtual_memory().total / (1024**3)
    persistence_tasks = 250 if ram_gb < 8 else 400
    idem_cycles = 6 if ram_gb < 8 else 8
    destructive = destructive_persistence_validation(task_count=persistence_tasks)
    idempotency = idempotency_validation(task_count=persistence_tasks, cycles=idem_cycles)
    persistence_pass = bool(destructive.get("passed") and idempotency.get("passed"))
    persistence = {"destructive": destructive, "idempotency": idempotency}
    registry.record("persistence_recovery", ValidationEvidence("windows-v11-persistence", "physical", "windows-target", persistence_pass, json.dumps(persistence, default=str)))

    scheduler = await scheduler_physical(outdir)
    registry.record("scheduler", ValidationEvidence("windows-v11-scheduler", "physical", "windows-target", bool(scheduler["passed"]), json.dumps(scheduler, default=str)))

    gates = StrictReleaseGates().assess(registry)
    physical_core_pass = all([
        app_launch.get("passed", False),
        resource_pass,
        dp_ok,
        cm_ok,
        browser.get("passed", False),
        persistence_pass,
        scheduler.get("passed", False),
    ])
    report = {
        "phase": "WINDOWS_PHYSICAL_GATE_V11",
        "environment": {
            "platform": "windows",
            "logical_cpus": psutil.cpu_count(logical=True),
            "ram_gb": round(ram_gb, 2),
        },
        "installed_app_launch": app_launch,
        "resource_governor": resource,
        "credentials": credentials,
        "browser_worker": browser,
        "persistence_recovery": persistence,
        "scheduler": scheduler,
        "physical_core_pass": physical_core_pass,
        "release_gates_after_physical": gates,
        "maturity_summary": registry.summary(),
        "next_required_for_validated_gate": "Live real-provider conversation_controller validation (>=2 turns, 0 human continue prompts).",
    }
    json_path = outdir / "WINDOWS_PHYSICAL_VALIDATION_V11.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    txt_path = outdir / "VALIDATION_SUMMARY_V11.txt"
    txt_path.write_text(
        "\n".join([
            "CEO de IAs - Windows Physical Validation v11",
            f"Installed app/API: {'PASS' if app_launch.get('passed') else 'FAIL'}",
            f"Resource governor: {'PASS' if resource_pass else 'FAIL'}",
            f"DPAPI: {'PASS' if dp_ok else 'FAIL'}",
            f"Credential Manager: {'PASS' if cm_ok else 'FAIL'}",
            f"Browser worker launch: {'PASS' if browser.get('passed') else 'FAIL'}",
            f"Persistence recovery: {'PASS' if persistence_pass else 'FAIL'}",
            f"Scheduler physical run: {'PASS' if scheduler.get('passed') else 'FAIL'}",
            f"PHYSICAL CORE: {'PASS' if physical_core_pass else 'FAIL'}",
            f"Release channel after this run: {gates.get('highest_channel')}",
            "Next: live real-provider Conversation Controller validation; do not mark VALIDATED before it passes.",
        ]),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\nRESULTS: {outdir}")
    print(f"SUMMARY: {txt_path}")
    return 0 if physical_core_pass else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
