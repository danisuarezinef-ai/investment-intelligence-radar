from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_field import (
    FIELD_MISSIONS,
    FieldGateAntiSpoofing,
    FieldMissionGate,
    UnifiedFieldEvidenceLedger,
)

PROJECT_ID = "windows-self-hosting-field"
RESULT = Path.home() / "Desktop" / "CEO_AI_GATE_TO_WORK_RESULT.json"


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
            "attestation_verified": bool((row.get("attestation") or {}).get("verified")),
        }
        for name, row in statuses.items()
    }


def _write(payload):
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    print(f"\n[CEO] Resultado: {RESULT}")




def _parse_child_payload(text: str) -> dict:
    """Parse the validator JSON without trusting surrounding console noise."""
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(raw):
            if ch != "{":
                continue
            try:
                data, end = decoder.raw_decode(raw[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and raw[idx + end:].strip() == "":
                return data
        return {}


def _reconcile_child_attestation(
    catalog: ProjectCatalog,
    mission: str,
    child_payload: dict,
    *,
    ledger: UnifiedFieldEvidenceLedger | None = None,
) -> dict:
    """Merge only a cryptographically valid child field row into the canonical store.

    This repairs cross-process checkpoint visibility without weakening the gate: the
    child row must have a valid local HMAC, the expected mission id, source/platform
    rules and every required claim before it can be copied.
    """
    ledger = ledger or UnifiedFieldEvidenceLedger()
    row = child_payload.get("result") if isinstance(child_payload, dict) else None
    if not isinstance(row, dict):
        return {"reconciled": False, "reason": "child_result_missing"}
    if row.get("mission") != mission:
        return {"reconciled": False, "reason": "mission_mismatch", "child_mission": row.get("mission")}
    spec = next((x for x in FIELD_MISSIONS if x.mission == mission), None)
    if spec is None:
        return {"reconciled": False, "reason": "unknown_mission"}
    verdict = ledger.verify(row, require_windows=spec.require_windows)
    claims = {
        str(item.get("kind"))
        for item in row.get("items", [])
        if str(item.get("value", "")).lower() in {"true", "pass", "verified", "1"}
    }
    missing_claims = sorted(set(spec.required_claims) - claims)
    if not verdict.get("verified") or missing_claims:
        return {
            "reconciled": False,
            "reason": "child_attestation_invalid",
            "verification": verdict,
            "missing_claims": missing_claims,
        }

    store, state = _load(catalog)
    gate = FieldMissionGate(FieldGateAntiSpoofing(ledger))
    before = gate.status(state, spec)
    if before.get("verified") is True:
        return {"reconciled": False, "reason": "already_persisted", "verified": True}

    run_id = str(row.get("run_id") or "")
    if not run_id:
        return {"reconciled": False, "reason": "run_id_missing"}
    bucket = state.metadata.setdefault(ledger.KEY, {})
    existing = bucket.get(run_id)
    if existing is not None and existing != row:
        return {"reconciled": False, "reason": "run_id_collision"}
    bucket[run_id] = row
    state.metadata.setdefault("cross_process_attestation_recovery_v1", []).append({
        "mission": mission,
        "run_id": run_id,
        "source": "signed_child_stdout",
        "reconciled_at": datetime.now(timezone.utc).isoformat(),
    })
    state.metadata["cross_process_attestation_recovery_v1"] = state.metadata["cross_process_attestation_recovery_v1"][-50:]
    store.save(state)
    catalog.touch(state)

    _, reloaded = _load(catalog)
    after = gate.status(reloaded, spec)
    return {
        "reconciled": after.get("verified") is True,
        "reason": "signed_child_attestation_imported" if after.get("verified") is True else "post_import_gate_not_verified",
        "run_id": run_id,
        "verification": verdict,
        "missing_claims": missing_claims,
        "after_status": after.get("status"),
    }


def _recover_packaged_attestations(catalog: ProjectCatalog) -> list[dict]:
    """Recover prior signed child output bundled by the operator, if still valid."""
    recovered: list[dict] = []
    folder = ROOT / "recovery_inputs"
    if not folder.exists():
        return recovered
    for path in sorted(folder.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        diagnostic = payload.get("mission_81_diagnostic") if isinstance(payload, dict) else None
        stdout = diagnostic.get("stdout_tail", "") if isinstance(diagnostic, dict) else ""
        child = _parse_child_payload(stdout)
        if child:
            row = child.get("result") or {}
            mission = row.get("mission")
            if mission in {"chatgpt_worker", "chatgpt_multiturn"}:
                result = _reconcile_child_attestation(catalog, mission, child)
                result["input"] = path.name
                recovered.append(result)
    return recovered


def _run_script(name: str, *args: str) -> tuple[int, dict, dict]:
    # Every field child uses the catalog's active project. Re-canonicalize before
    # each subprocess so a stale/temporary active id cannot redirect mission 81/82.
    try:
        catalog = ProjectCatalog(user_data_root() / "projects")
        _load(catalog)
    except Exception as exc:
        return 98, {
            "returncode": 98,
            "stdout_tail": "",
            "stderr_tail": f"canonical_project_repair_failed: {type(exc).__name__}: {exc}",
        }, {}
    cmd = [sys.executable, str(ROOT / "scripts" / name), *args]
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
    # Echo child output for the operator while also retaining a bounded diagnostic.
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="" if proc.stderr.endswith("\n") else "\n")
    diag = {
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:] if proc.stdout else "",
        "stderr_tail": proc.stderr[-4000:] if proc.stderr else "",
    }
    key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if key:
        diag["stdout_tail"] = diag["stdout_tail"].replace(key, "<redacted-api-key>")
        diag["stderr_tail"] = diag["stderr_tail"].replace(key, "<redacted-api-key>")
    return proc.returncode, diag, _parse_child_payload(proc.stdout)


def _load(catalog: ProjectCatalog):
    store = catalog.store(PROJECT_ID)
    state = store.load()
    if state is None:
        raise RuntimeError("canonical_project_missing")
    if state.id != PROJECT_ID:
        previous_id = state.id
        history = list(state.metadata.get("project_identity_recovery_v1", []))
        history.append({
            "from": previous_id,
            "to": PROJECT_ID,
            "reason": "canonical_field_store_id_mismatch",
            "repaired_at": datetime.now(timezone.utc).isoformat(),
        })
        state.metadata["project_identity_recovery_v1"] = history[-20:]
        state.id = PROJECT_ID
        store.save(state)
    catalog.register(state, make_active=True)
    # Explicitly assert the catalog pointer after register.
    if catalog.active_project_id() != PROJECT_ID:
        catalog.set_active(PROJECT_ID)
    return store, state


def main() -> int:
    if os.name != "nt":
        _write({"status": "NOT_RUN", "reason": "windows_required", "production_verified": False})
        return 2

    if not os.getenv("GEMINI_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        _write({
            "status": "BLOCKED",
            "reason": "no_live_ai_provider_configured",
            "next": "run_the_secure_gemini_launcher",
            "production_verified": False,
        })
        return 3

    catalog = ProjectCatalog(user_data_root() / "projects")
    try:
        _, state = _load(catalog)
    except Exception as exc:
        _write({
            "status": "BLOCKED",
            "reason": "canonical_project_missing",
            "error": f"{type(exc).__name__}: {exc}",
            "production_verified": False,
        })
        return 4

    packaged_recovery = _recover_packaged_attestations(catalog)
    if packaged_recovery:
        print("[CEO] Reconciliacion previa de attestations firmadas:")
        print(json.dumps(packaged_recovery, indent=2, ensure_ascii=False, default=str))
        _, state = _load(catalog)

    statuses = _status_map(state)
    required_pre_ai = ["windows_read_only", "chrome_navigation", "chrome_session", "download", "multi_app"]
    missing_pre_ai = [m for m in required_pre_ai if statuses[m]["verified"] is not True]
    if missing_pre_ai:
        _write({
            "status": "BLOCKED",
            "reason": "pre_ai_field_chain_not_verified",
            "missing": missing_pre_ai,
            "statuses": _compact(statuses),
            "production_verified": False,
        })
        return 5

    print("\n=== CEO — RECUPERACION MINIMA DE AI GATES 81-82 ===")
    print("Se repetiran SOLO las misiones IA que falten.")
    print("Gemini/API key vive solo en este proceso; CEO no compra creditos ni activa billing.")
    print("Sin auto-promocion y sin Git de red.\n")

    rc81 = 0
    diag81 = {}
    if statuses["chatgpt_worker"]["verified"] is not True:
        print("[CEO] Ejecutando mision 81: AI Worker Live...")
        rc81, diag81, child81 = _run_script("validate_self_hosting_field.py", "--mission", "chatgpt_worker")
        reconcile81 = _reconcile_child_attestation(catalog, "chatgpt_worker", child81) if child81 else {"reconciled": False, "reason": "no_child_payload"}
        _, state = _load(catalog)
        statuses = _status_map(state)
    if statuses["chatgpt_worker"]["verified"] is not True:
        _write({
            "status": "BLOCKED",
            "reason": "mission_81_not_verified",
            "mission_81_returncode": rc81,
            "mission_81_diagnostic": diag81,
            "mission_81_reconciliation": locals().get("reconcile81", {}),
            "provider_failure": state.metadata.get("last_ai_field_failure"),
            "statuses": _compact(statuses),
            "next": "inspect_only_mission_81_provider_failure",
            "production_verified": False,
        })
        return 6

    rc82 = 0
    diag82 = {}
    if statuses["chatgpt_multiturn"]["verified"] is not True:
        print("[CEO] Ejecutando mision 82: AI Worker Multi-Turn...")
        rc82, diag82, child82 = _run_script("validate_self_hosting_field.py", "--mission", "chatgpt_multiturn")
        reconcile82 = _reconcile_child_attestation(catalog, "chatgpt_multiturn", child82) if child82 else {"reconciled": False, "reason": "no_child_payload"}
        _, state = _load(catalog)
        statuses = _status_map(state)
    if statuses["chatgpt_multiturn"]["verified"] is not True:
        _write({
            "status": "BLOCKED",
            "reason": "mission_82_not_verified",
            "mission_81_returncode": rc81,
            "mission_82_returncode": rc82,
            "mission_81_diagnostic": diag81,
            "mission_82_diagnostic": diag82,
            "mission_82_reconciliation": locals().get("reconcile82", {}),
            "provider_failure": state.metadata.get("last_ai_field_failure"),
            "statuses": _compact(statuses),
            "next": "inspect_only_mission_82_context_failure",
            "production_verified": False,
        })
        return 7

    # Historical mission 83 already has a recovered signed row. Once 81/82 are
    # restored, normal prerequisite evaluation may make it valid automatically.
    if statuses["self_improvement_field"]["verified"] is not True:
        print("[CEO] Reescaneando evidencia historica para mision 83...")
        _run_script("recover_historical_field_evidence.py")
        _, state = _load(catalog)
        statuses = _status_map(state)

    rc83 = 0
    if statuses["self_improvement_field"]["verified"] is not True:
        print("[CEO] Mision 83 aun no verifica. Ejecutando el attestor normal sobre evidencia real existente...")
        rc83, _, _ = _run_script("validate_self_hosting_field.py", "--mission", "self_improvement_field")
        _, state = _load(catalog)
        statuses = _status_map(state)
    if statuses["self_improvement_field"]["verified"] is not True:
        _write({
            "status": "PARTIAL",
            "reason": "mission_83_still_not_verified",
            "mission_81_returncode": rc81,
            "mission_82_returncode": rc82,
            "mission_83_returncode": rc83,
            "statuses": _compact(statuses),
            "next": "repair_only_mission_83_if_real_candidate_metadata_is_missing",
            "production_verified": False,
        })
        return 8

    rc84 = 0
    if statuses["alpha_certification"]["verified"] is not True:
        print("\n[CEO] 76-83 estan verificadas. Falta reemitir Alpha (84).")
        print("[CEO] Confirma solo si la prueba fisica previa de recovery/restart fue realmente realizada.")
        answer = input("[CEO] Confirmas recovery/resume fisico ya verificado? [S/N]: ").strip().lower()
        if answer not in {"s", "si", "sí", "y", "yes"}:
            _write({
                "status": "PARTIAL",
                "reason": "alpha_recovery_confirmation_not_granted",
                "mission_81_returncode": rc81,
                "mission_82_returncode": rc82,
                "statuses": _compact(statuses),
                "next": "confirm_only_if_prior_physical_recovery_test_was_really_done",
                "production_verified": False,
            })
            return 9
        rc84, _, _ = _run_script("validate_self_hosting_field.py", "--mission", "alpha_certification", "--confirm-recovery-verified")
        _, state = _load(catalog)
        statuses = _status_map(state)

    alpha_ok = statuses["alpha_certification"]["verified"] is True
    payload = {
        "status": "PASS" if alpha_ok else "PARTIAL",
        "project_id": PROJECT_ID,
        "mission_81_returncode": rc81,
        "mission_82_returncode": rc82,
        "mission_83_returncode": rc83,
        "mission_84_returncode": rc84,
        "alpha_verified": alpha_ok,
        "packaged_attestation_recovery": packaged_recovery,
        "mission_81_reconciliation": locals().get("reconcile81", {}),
        "mission_82_reconciliation": locals().get("reconcile82", {}),
        "statuses": _compact(statuses),
        "next": "start_work_session_001" if alpha_ok else "inspect_only_remaining_gate",
        "production_verified": False,
    }
    _write(payload)
    if not alpha_ok:
        return 10

    print("\n[CEO] Alpha verificada. Iniciando Work Session 001...\n")
    rc_work, _, _ = _run_script("run_first_ceo_work_session.py")
    return rc_work


if __name__ == "__main__":
    raise SystemExit(main())
