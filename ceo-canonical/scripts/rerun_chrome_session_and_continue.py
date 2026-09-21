from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_field import FIELD_MISSIONS, FieldMissionGate, SelfHostingFieldOpsCore
from scripts.validate_self_hosting_field import _chrome_controller, claim, prerequisite

PROJECT_ID = "windows-self-hosting-field"
RESULT = Path.home() / "Desktop" / "CEO_MINIMAL_FIELD_GAP_RESULT.json"


def _status_map(state):
    gate = FieldMissionGate()
    return {spec.mission: gate.status(state, spec) for spec in FIELD_MISSIONS}


def _compact(statuses):
    return {
        name: {
            "status": row.get("status"),
            "verified": bool(row.get("verified")),
            "claims_present": row.get("claims_present", []),
            "prerequisites_ok": row.get("prerequisites_ok"),
        }
        for name, row in statuses.items()
    }


def _write(payload):
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


async def _safe_stop(ctrl, cleanup_errors: list[dict], stage: str) -> None:
    """Close Chrome without allowing an already-closed browser to erase mission evidence."""
    try:
        await ctrl.stop()
    except Exception as exc:
        row = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
        cleanup_errors.append(row)
        msg = str(exc).lower()
        benign = (
            type(exc).__name__ == "TargetClosedError"
            or "target page, context or browser has been closed" in msg
            or "event loop is closed" in msg
        )
        if not benign:
            raise


async def rerun_chrome_session(core, state, cleanup_errors: list[dict]) -> dict:
    prerequisite(core, state, "chrome_navigation")
    run = core.ledger.begin(state, mission="chrome_session", platform_name="windows")
    session_id = "field-authenticated"
    ctrl, _ = await _chrome_controller(state, session_id)
    session1 = None
    try:
        await ctrl.navigate("https://example.com")
        session1 = ctrl.sessions.get_or_create(state, session_id)
        claim(core, state, run["run_id"], "dedicated_profile", profile_dir=session1.profile_dir)
        print("\n[CEO] Chrome se ha abierto con el perfil dedicado de CEO.")
        print("[CEO] Comprueba visualmente que es el perfil/sesion que ya usaste en la validacion.")
        answer = input("[CEO] Confirmas que esta sesion dedicada es la autenticada/reutilizable? [S/N]: ").strip().lower()
        if answer not in {"s", "si", "sí", "y", "yes"}:
            return core.ledger.finalize(state, run["run_id"], success=False)
        claim(core, state, run["run_id"], "manual_login_once", confirmation="operator confirmed visible dedicated authenticated session")
    finally:
        await _safe_stop(ctrl, cleanup_errors, "first_chrome_context")

    ctrl2, _ = await _chrome_controller(state, session_id)
    try:
        session2 = ctrl2.sessions.get_or_create(state, session_id)
        if session1 is not None and session1.profile_dir == session2.profile_dir:
            claim(core, state, run["run_id"], "session_reused", profile_dir=session2.profile_dir)
        serialized = json.dumps(state.metadata.get("chrome_sessions_v1", {}), default=str).lower()
        forbidden = any(x in serialized for x in ("password", "cookie", "credential", "secret", "token"))
        if not forbidden:
            claim(core, state, run["run_id"], "no_credentials_in_state")
        return core.ledger.finalize(state, run["run_id"], success=not forbidden)
    finally:
        await _safe_stop(ctrl2, cleanup_errors, "second_chrome_context")


def _run_script(name: str, *args: str) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / name), *args]
    return subprocess.run(cmd, cwd=str(ROOT), check=False).returncode


def main() -> int:
    if os.name != "nt":
        _write({"status": "NOT_RUN", "reason": "windows_required", "production_verified": False})
        return 2

    catalog = ProjectCatalog(user_data_root() / "projects")
    store = catalog.store(PROJECT_ID)
    state = store.load()
    if state is None:
        _write({"status": "BLOCKED", "reason": "canonical_project_missing", "production_verified": False})
        return 3

    catalog.register(state, make_active=True)
    before = _status_map(state)
    if before["chrome_navigation"]["verified"] is not True:
        _write({
            "status": "BLOCKED",
            "reason": "chrome_navigation_not_verified",
            "before": _compact(before),
            "next": "restore_or_rerun_chrome_navigation_only",
            "production_verified": False,
        })
        return 4

    core = SelfHostingFieldOpsCore()
    cleanup_errors: list[dict] = []
    print("\n=== CEO — RECUPERACION MINIMA DE FIELD GAP ===")
    print("Se repetira SOLO chrome_session (mision 78).")
    print("No hay promocion, Git de red ni gasto automatico.\n")

    try:
        row = asyncio.run(rerun_chrome_session(core, state, cleanup_errors))
    except Exception as exc:
        # Always leave a Desktop artifact, even for an unexpected bridge failure.
        _write({
            "status": "FAILED",
            "reason": "chrome_session_bridge_exception",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "cleanup_errors": cleanup_errors,
            "next": "fix_only_the_recorded_bridge_failure",
            "production_verified": False,
        })
        return 10
    store.save(state)
    catalog.register(state, make_active=True)
    after_78 = _status_map(state)
    if after_78["chrome_session"]["verified"] is not True:
        _write({
            "status": "BLOCKED",
            "reason": "chrome_session_revalidation_failed",
            "run": row,
            "after_chrome_session": _compact(after_78),
            "next": "inspect_chrome_session_only",
            "cleanup_errors": cleanup_errors,
            "production_verified": False,
        })
        return 5

    # Re-scan immutable historical stores now that the missing prerequisite is restored.
    scan_rc = _run_script("recover_historical_field_evidence.py")
    state = store.load()
    statuses = _status_map(state)

    if statuses["alpha_certification"]["verified"] is not True:
        alpha_prereqs_ok = (
            statuses["self_improvement_field"]["verified"] is True
            and statuses["chatgpt_multiturn"]["verified"] is True
        )
        if alpha_prereqs_ok:
            print("\n[CEO] La cadena 76-83 vuelve a ser verificable, pero falta reemitir Alpha.")
            print("[CEO] Alpha exige confirmar que la recuperacion/reanudacion Windows ya fue verificada fisicamente.")
            answer = input("[CEO] Confirmas esa validacion de recovery/resume previa? [S/N]: ").strip().lower()
            if answer in {"s", "si", "sí", "y", "yes"}:
                alpha_rc = _run_script("validate_self_hosting_field.py", "--mission", "alpha_certification", "--confirm-recovery-verified")
                state = store.load()
                statuses = _status_map(state)
            else:
                alpha_rc = 9
        else:
            alpha_rc = 8
    else:
        alpha_rc = 0

    alpha_ok = statuses["alpha_certification"]["verified"] is True
    payload = {
        "status": "PASS" if alpha_ok else "PARTIAL",
        "project_id": PROJECT_ID,
        "chrome_session_verified": statuses["chrome_session"]["verified"],
        "historical_rescan_returncode": scan_rc,
        "alpha_returncode": alpha_rc,
        "alpha_verified": alpha_ok,
        "statuses": _compact(statuses),
        "next": "start_work_session_001" if alpha_ok else "inspect_only_remaining_unverified_gate",
        "cleanup_errors": cleanup_errors,
        "production_verified": False,
    }
    _write(payload)
    if not alpha_ok:
        return 6

    print("\n[CEO] Alpha vuelve a estar verificada. Iniciando Work Session 001...\n")
    work_rc = _run_script("run_first_ceo_work_session.py")
    return work_rc


if __name__ == "__main__":
    raise SystemExit(main())
