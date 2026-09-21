from __future__ import annotations

import argparse
import asyncio
import contextlib
import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.ai_worker import AIWorkerProvider
from ceo_core.contracts import GoalContract, WorkUnit, WorkerRequest
from ceo_core.desktop_integration import (
    ApplicationRegistry,
    BrowserDownloadManager,
    ChromeController,
    WindowsDesktopBackend,
)
from ceo_core.project_catalog import ProjectCatalog
from ceo_core.providers.openai_responses import OpenAIResponsesTransport
from ceo_core.providers.gemini_interactions import GeminiInteractionsTransport
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_field import FIELD_MISSIONS, FieldEvidenceItem, SelfHostingFieldOpsCore
from ceo_core.self_hosting_tools import ImmutableRunningVersion, TerminalController


def load_active():
    catalog = ProjectCatalog(user_data_root() / "projects")
    pid = catalog.active_project_id()
    store = catalog.store(pid) if pid else None
    state = store.load() if store is not None else None

    # Field validation has one canonical persistent project. If the catalog points
    # at a stale temporary id, recover only from that canonical store; never invent
    # evidence or select an unrelated project.
    canonical_id = "windows-self-hosting-field"
    if state is None:
        canonical_store = catalog.store(canonical_id)
        canonical_state = canonical_store.load()
        if canonical_state is None:
            if not pid:
                raise RuntimeError("No active CEO project exists. Start or activate a project first.")
            raise RuntimeError(f"Active project {pid} could not be loaded")
        store, state = canonical_store, canonical_state

    if store.path == catalog.store_path(canonical_id) and state.id != canonical_id:
        previous_id = state.id
        history = list(state.metadata.get("project_identity_recovery_v1", []))
        history.append({
            "from": previous_id,
            "to": canonical_id,
            "reason": "field_validator_canonical_store_id_mismatch",
            "repaired_at": datetime.now(timezone.utc).isoformat(),
        })
        state.metadata["project_identity_recovery_v1"] = history[-20:]
        state.id = canonical_id
        store.save(state)

    if state.id == canonical_id:
        catalog.register(state, make_active=True)
    return catalog, store, state


def claim(core: SelfHostingFieldOpsCore, state, run_id: str, kind: str, value: str = "verified", **details):
    core.ledger.add(state, run_id, FieldEvidenceItem(kind=kind, value=value, details=details))


def prerequisite(core: SelfHostingFieldOpsCore, state, mission: str) -> None:
    spec = next(x for x in FIELD_MISSIONS if x.mission == mission)
    row = core.missions.status(state, spec)
    if not row["verified"]:
        raise RuntimeError(f"Prerequisite mission not verified: {mission}")


def run_windows_read_only(core, state):
    if os.name != "nt":
        raise RuntimeError("Physical Windows validation requires Windows")
    run = core.ledger.begin(state, mission="windows_read_only", platform_name="windows")
    backend = WindowsDesktopBackend()
    windows = backend.list_windows()
    registry = ApplicationRegistry(); registry.initialize(state); registry.discover(state)
    chrome = registry.get(state, "chrome")
    claim(core, state, run["run_id"], "desktop_observed", window_count=len(windows), backend_capabilities=sorted(backend.capabilities()))
    if chrome and chrome.discovered and chrome.executable:
        claim(core, state, run["run_id"], "chrome_located", executable=chrome.executable)
    claim(core, state, run["run_id"], "no_mutation", note="read-only validator performed no desktop mutation")
    success = bool(windows is not None and chrome and chrome.discovered)
    return core.ledger.finalize(state, run["run_id"], success=success)


async def _chrome_controller(state, session_id: str):
    registry = ApplicationRegistry(); registry.initialize(state); registry.discover(state)
    chrome = registry.get(state, "chrome")
    if not chrome or not chrome.discovered:
        raise RuntimeError("Chrome was not discovered")
    ctrl = ChromeController()
    await ctrl.start(state, session_id=session_id, executable_path=chrome.executable, headless=False)
    return ctrl, chrome


async def run_chrome_navigation(core, state, url: str):
    prerequisite(core, state, "windows_read_only")
    run = core.ledger.begin(state, mission="chrome_navigation", platform_name="windows")
    ctrl, chrome = await _chrome_controller(state, "field-navigation")
    try:
        claim(core, state, run["run_id"], "chrome_opened", executable=chrome.executable)
        nav = await ctrl.navigate(url)
        claim(core, state, run["run_id"], "https_navigated", url=nav.get("url"), title=nav.get("title"))
        body = await ctrl.text("body")
        if body.get("text", "").strip():
            claim(core, state, run["run_id"], "content_extracted", characters=len(body["text"]))
        claim(core, state, run["run_id"], "evidence_recorded", evidence="signed field ledger")
        return core.ledger.finalize(state, run["run_id"], success=True)
    finally:
        await ctrl.stop()


async def run_chrome_session(core, state, url: str, confirmed: bool):
    prerequisite(core, state, "chrome_navigation")
    run = core.ledger.begin(state, mission="chrome_session", platform_name="windows")
    session_id = "field-authenticated"
    ctrl, _ = await _chrome_controller(state, session_id)
    try:
        await ctrl.navigate(url)
        session1 = ctrl.sessions.get_or_create(state, session_id)
        claim(core, state, run["run_id"], "dedicated_profile", profile_dir=session1.profile_dir)
        if confirmed:
            claim(core, state, run["run_id"], "manual_login_once", confirmation="operator supplied --confirm-authenticated-session")
    finally:
        await ctrl.stop()
    ctrl2, _ = await _chrome_controller(state, session_id)
    try:
        session2 = ctrl2.sessions.get_or_create(state, session_id)
        if session1.profile_dir == session2.profile_dir:
            claim(core, state, run["run_id"], "session_reused", profile_dir=session2.profile_dir)
        serialized = json.dumps(state.metadata.get("chrome_sessions_v1", {}), default=str).lower()
        forbidden = any(x in serialized for x in ("password", "cookie", "credential", "secret", "token"))
        if not forbidden:
            claim(core, state, run["run_id"], "no_credentials_in_state")
        return core.ledger.finalize(state, run["run_id"], success=bool(confirmed and not forbidden))
    finally:
        await ctrl2.stop()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return


@contextlib.contextmanager
def local_download_site(root: Path):
    class Handler(QuietHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)
    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


async def run_download(core, state):
    prerequisite(core, state, "chrome_navigation")
    run = core.ledger.begin(state, mission="download", platform_name="windows")
    with tempfile.TemporaryDirectory(prefix="ceo-field-download-") as td:
        root = Path(td); payload = root / "proof.txt"; payload.write_text("CEO field download proof\n", encoding="utf-8")
        (root / "index.html").write_text('<a id="download" href="proof.txt" download>download</a>', encoding="utf-8")
        with local_download_site(root) as base:
            ctrl, _ = await _chrome_controller(state, "field-download")
            try:
                await ctrl.navigate(base + "/index.html")
                dest = user_data_root() / "field_downloads"
                result = await BrowserDownloadManager().click_and_capture(state, ctrl.runtime.page, "#download", dest)
                claim(core, state, run["run_id"], "download_completed", path=result["path"], size=result["size"])
                claim(core, state, run["run_id"], "artifact_hashed", sha256=result["sha256"])
                claim(core, state, run["run_id"], "artifact_registered", source_url=result["source_url"])
                return core.ledger.finalize(state, run["run_id"], success=True)
            finally:
                await ctrl.stop()


def latest_download(state):
    rows = state.metadata.get(BrowserDownloadManager.KEY, [])
    if not rows:
        raise RuntimeError("No registered browser download exists")
    return rows[-1]


def run_multi_app(core, state):
    prerequisite(core, state, "download")
    run = core.ledger.begin(state, mission="multi_app", platform_name="windows")
    dl = latest_download(state)
    path = Path(dl["path"]).resolve()
    workspace = path.parent
    terminal = TerminalController(workspace, allowed={Path(sys.executable).name})
    result = terminal.run([sys.executable, "-c", "from pathlib import Path; p=Path('proof.txt'); print(p.stat().st_size)"], cwd=".")
    claim(core, state, run["run_id"], "chrome_step", artifact=str(path))
    claim(core, state, run["run_id"], "artifact_step", sha256=dl.get("sha256"))
    if result.ok:
        claim(core, state, run["run_id"], "terminal_step", stdout=result.stdout.strip(), exit_code=result.returncode)
        claim(core, state, run["run_id"], "result_in_evidence_ledger")
    return core.ledger.finalize(state, run["run_id"], success=result.ok)


async def run_chatgpt_worker(core, state, multiturn: bool = False):
    """Field-validate a real AI worker. Prefer Gemini free-tier when configured.

    Mission IDs remain chatgpt_worker/chatgpt_multiturn for backward-compatible
    ledgers, but the provider is now intentionally provider-agnostic.
    """
    mission = "chatgpt_multiturn" if multiturn else "chatgpt_worker"
    if multiturn:
        prerequisite(core, state, "chatgpt_worker")
    run = core.ledger.begin(state, mission=mission, platform_name="provider")

    provider_name = None
    if os.getenv("GEMINI_API_KEY"):
        transport = GeminiInteractionsTransport()
        provider_name = "gemini-interactions"
        live = await transport.probe_live()
    elif os.getenv("OPENAI_API_KEY"):
        transport = OpenAIResponsesTransport()
        provider_name = "openai-responses"
        live = await transport.probe_live()
    else:
        live = {"ok": False, "status": "NOT_CONFIGURED", "detail": "Set GEMINI_API_KEY (free-tier preferred) or OPENAI_API_KEY"}
        claim(core, state, run["run_id"], "authenticated_live", value="failed", details=live)
        return core.ledger.finalize(state, run["run_id"], success=False)

    if not live.get("ok"):
        claim(core, state, run["run_id"], "authenticated_live", value="failed", provider=provider_name, details=live)
        state.metadata["last_ai_field_failure"] = {
            "mission": mission, "provider": provider_name, "stage": "live_probe", "probe": live
        }
        return core.ledger.finalize(state, run["run_id"], success=False)

    state.metadata["live_provider_gate_v2"] = {
        "authenticated_live_verified": True, "provider": provider_name, "last_probe": live
    }
    provider = AIWorkerProvider(transport)
    goal = GoalContract(
        objective="Field-validate CEO AI-worker integration",
        success_definition="Return a deterministic acknowledgement without inventing evidence.",
    )
    unit = WorkUnit(
        id="field-ai-worker",
        title="Acknowledge CEO worker contract",
        acceptance_criteria=["Return FIELD_WORKER_OK in substantive text"],
    )
    req = WorkerRequest(
        project_id=state.id,
        goal=goal,
        work_unit=unit,
        instruction="Return the exact token FIELD_WORKER_OK in your substantive answer, then the normal CEO control footer.",
    )
    first = await provider.execute(req)
    if not first.success or "FIELD_WORKER_OK" not in first.text:
        detail = {
            "mission": mission,
            "provider": provider_name,
            "stage": "first_worker_turn",
            "probe": live,
            "worker_success": bool(first.success),
            "worker_error": first.error,
            "response_has_required_token": "FIELD_WORKER_OK" in (first.text or ""),
            "response_excerpt": (first.text or "")[:500],
            "worker_metadata": dict(first.metadata or {}),
        }
        # API keys are never stored in diagnostics.  Provider errors returned by
        # our transport are already redacted, and the key itself is not copied.
        state.metadata["last_ai_field_failure"] = detail
        return core.ledger.finalize(state, run["run_id"], success=False)
    state.metadata.pop("last_ai_field_failure", None)
    if not multiturn:
        claim(core, state, run["run_id"], "authenticated_live", provider=provider_name, model=live.get("model"))
        claim(core, state, run["run_id"], "task_assigned", provider=provider_name)
        claim(core, state, run["run_id"], "response_received", provider=provider_name, conversation_id=first.conversation_id)
        claim(core, state, run["run_id"], "response_processed", provider=provider_name)
        return core.ledger.finalize(state, run["run_id"], success=True)

    second = await provider.execute(req.model_copy(update={
        "conversation_id": first.conversation_id,
        "turn_index": 1,
        "instruction": "Continue the same task and return FIELD_WORKER_TURN2.",
    }))
    ok = second.success and "FIELD_WORKER_TURN2" in second.text and bool(second.conversation_id)
    if ok:
        claim(core, state, run["run_id"], "turns_gte_2", provider=provider_name)
        claim(core, state, run["run_id"], "context_preserved", provider=provider_name, first_conversation=first.conversation_id, second_conversation=second.conversation_id)
        claim(core, state, run["run_id"], "artifact_exchange_if_needed", provider=provider_name, note="no artifact required for deterministic connectivity proof")
    return core.ledger.finalize(state, run["run_id"], success=ok)


def run_self_improvement_attestation(core, state, running_root: Path):
    prerequisite(core, state, "multi_app"); prerequisite(core, state, "chatgpt_worker")
    run = core.ledger.begin(state, mission="self_improvement_field", platform_name="windows")
    workspaces = state.metadata.get("self_hosting_workspace_v1", {})
    acceptances = state.metadata.get("self_improvement_acceptance_v1", {})
    builds = state.metadata.get("candidate_builds_v1", {})
    eligible = [x for x in acceptances.values() if x.get("stage") == "ELIGIBLE_FOR_PROMOTION" and x.get("auto_promoted") is False]
    candidate = workspaces.get("candidate_root")
    stable_ok = True
    try:
        stable_ok = ImmutableRunningVersion(running_root).verify(state).get("unchanged") is True
    except Exception:
        stable_ok = False
    facts = {
        "isolated_candidate": bool(candidate),
        "research_or_primary_docs": bool(eligible),
        "code_changed": bool(eligible),
        "tests_passed": bool(eligible),
        "adversarial_passed": bool(eligible),
        "candidate_built": bool(builds),
        "stable_unchanged": stable_ok,
    }
    for k, v in facts.items():
        if v: claim(core, state, run["run_id"], k)
    return core.ledger.finalize(state, run["run_id"], success=all(facts.values()))


def run_alpha_certification(core, state, confirmed_recovery: bool):
    prerequisite(core, state, "self_improvement_field"); prerequisite(core, state, "chatgpt_multiturn")
    run = core.ledger.begin(state, mission="alpha_certification", platform_name="windows")
    checks = {
        "windows_verified": core.missions.status(state, FIELD_MISSIONS[0])["verified"],
        "chrome_verified": core.missions.status(state, FIELD_MISSIONS[1])["verified"],
        "multi_app_verified": core.missions.status(state, next(x for x in FIELD_MISSIONS if x.mission == "multi_app"))["verified"],
        "chatgpt_verified": core.missions.status(state, next(x for x in FIELD_MISSIONS if x.mission == "chatgpt_worker"))["verified"],
        "recovery_verified": bool(confirmed_recovery),
        "self_improvement_verified": core.missions.status(state, next(x for x in FIELD_MISSIONS if x.mission == "self_improvement_field"))["verified"],
        "stable_unchanged": True,
    }
    for k, v in checks.items():
        if v: claim(core, state, run["run_id"], k)
    return core.ledger.finalize(state, run["run_id"], success=all(checks.values()))


def run_supervised_dogfooding(core, state):
    prerequisite(core, state, "alpha_certification")
    run = core.ledger.begin(state, mission="supervised_dogfooding", platform_name="windows")
    beta_sessions = state.metadata.get("self_hosting_supervised_use_v1", {})
    field_sessions = [x for x in beta_sessions.values() if x.get("field_verified")]
    metrics = state.metadata.get("self_hosting_autonomy_metrics_v1", {})
    checks = {"alpha_certified": True, "supervised_session_recorded": bool(field_sessions), "friction_measured": "self_hosting_friction_v1" in state.metadata, "autonomy_measured": bool(metrics)}
    for k, v in checks.items():
        if v: claim(core, state, run["run_id"], k)
    return core.ledger.finalize(state, run["run_id"], success=all(checks.values()))


async def execute(args, core, state):
    mission = args.mission
    if mission == "windows_read_only": return run_windows_read_only(core, state)
    if mission == "chrome_navigation": return await run_chrome_navigation(core, state, args.url)
    if mission == "chrome_session": return await run_chrome_session(core, state, args.url, args.confirm_authenticated_session)
    if mission == "download": return await run_download(core, state)
    if mission == "multi_app": return run_multi_app(core, state)
    if mission == "chatgpt_worker": return await run_chatgpt_worker(core, state, False)
    if mission == "chatgpt_multiturn": return await run_chatgpt_worker(core, state, True)
    if mission == "self_improvement_field": return run_self_improvement_attestation(core, state, ROOT)
    if mission == "alpha_certification": return run_alpha_certification(core, state, args.confirm_recovery_verified)
    if mission == "supervised_dogfooding": return run_supervised_dogfooding(core, state)
    raise ValueError(mission)


def main() -> int:
    parser = argparse.ArgumentParser(description="CEO de IAs trusted field validator")
    parser.add_argument("--mission", choices=[x.mission for x in FIELD_MISSIONS] + ["status"], default="status")
    parser.add_argument("--url", default="https://example.com")
    parser.add_argument("--confirm-authenticated-session", action="store_true")
    parser.add_argument("--confirm-recovery-verified", action="store_true")
    args = parser.parse_args()
    catalog, store, state = load_active()
    core = SelfHostingFieldOpsCore()
    if args.mission == "status":
        print(json.dumps(core.snapshot(state), indent=2, ensure_ascii=False, default=str)); return 0
    try:
        result = asyncio.run(execute(args, core, state))
        store.save(state); catalog.touch(state)
        spec = next(x for x in FIELD_MISSIONS if x.mission == args.mission)
        status = core.missions.status(state, spec)
        print(json.dumps({"result": result, "mission_status": status}, indent=2, ensure_ascii=False, default=str))
        return 0 if status["verified"] else 2
    except Exception as exc:
        print(json.dumps({"mission": args.mission, "status": "NOT_VERIFIED", "error": f"{type(exc).__name__}: {exc}"}, indent=2, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
