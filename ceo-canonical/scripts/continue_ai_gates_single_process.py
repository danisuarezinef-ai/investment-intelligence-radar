from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_field import FIELD_MISSIONS, SelfHostingFieldOpsCore
from scripts.validate_self_hosting_field import (
    run_alpha_certification,
    run_chatgpt_worker,
    run_self_improvement_attestation,
)

PROJECT_ID = "windows-self-hosting-field"
DESKTOP = Path.home() / "Desktop"
LOCAL_RESULTS = ROOT / "RESULTADOS_CEO"
RESULT_NAME = "CEO_SINGLE_PROCESS_AI_GATE_RESULT.json"


def _write(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    targets = [DESKTOP / RESULT_NAME, LOCAL_RESULTS / RESULT_NAME]
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        except Exception:
            pass
    print(text)
    print(f"\n[CEO] Resultado: {targets[0]}")
    print(f"[CEO] Copia local: {targets[1]}")


def _load_canonical():
    catalog = ProjectCatalog(user_data_root() / "projects")
    store = catalog.store(PROJECT_ID)
    state = store.load()
    if state is None:
        raise RuntimeError("canonical_project_missing")
    if state.id != PROJECT_ID:
        old = state.id
        history = list(state.metadata.get("project_identity_recovery_v1", []))
        history.append({
            "from": old,
            "to": PROJECT_ID,
            "reason": "single_process_ai_gate_canonicalization",
            "repaired_at": datetime.now(timezone.utc).isoformat(),
        })
        state.metadata["project_identity_recovery_v1"] = history[-50:]
        state.id = PROJECT_ID
    # Persist once unconditionally with the fixed SqliteCheckpointStore. This collapses
    # historical shadow project rows before rebuilding 81/82/84, so no stale row can
    # overwrite the newly signed evidence when Work Session 001 starts in a child process.
    store.save(state)
    catalog.register(state, make_active=True)
    if catalog.active_project_id() != PROJECT_ID:
        catalog.set_active(PROJECT_ID)
    return catalog, store, state


def _status(core: SelfHostingFieldOpsCore, state, mission: str) -> dict[str, Any]:
    spec = next(x for x in FIELD_MISSIONS if x.mission == mission)
    return core.missions.status(state, spec)


def _compact(core: SelfHostingFieldOpsCore, state) -> dict[str, Any]:
    out = {}
    for spec in FIELD_MISSIONS:
        row = core.missions.status(state, spec)
        out[spec.mission] = {
            "status": row.get("status"),
            "verified": bool(row.get("verified")),
            "claims_present": row.get("claims_present", []),
            "prerequisites_ok": row.get("prerequisites_ok"),
            "attestation_verified": bool((row.get("attestation") or {}).get("verified")),
        }
    return out


def _extract_child_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    diag = payload.get("mission_81_diagnostic")
    if not isinstance(diag, dict):
        return None
    raw = str(diag.get("stdout_tail") or "").strip()
    if not raw:
        return None
    try:
        child = json.loads(raw)
    except json.JSONDecodeError:
        dec = json.JSONDecoder()
        child = None
        for i, ch in enumerate(raw):
            if ch != "{":
                continue
            try:
                candidate, end = dec.raw_decode(raw[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                child = candidate
                break
        if child is None:
            return None
    row = child.get("result") if isinstance(child, dict) else None
    return row if isinstance(row, dict) else None


def _candidate_result_files() -> list[Path]:
    seen: set[str] = set()
    paths: list[Path] = []
    for folder in [DESKTOP, ROOT / "recovery_inputs"]:
        if not folder.exists():
            continue
        patterns = ["CEO_AI_GATE_TO_WORK_RESULT*.json", "*.json"] if folder.name == "recovery_inputs" else ["CEO_AI_GATE_TO_WORK_RESULT*.json"]
        for pattern in patterns:
            for p in folder.glob(pattern):
                try:
                    key = str(p.resolve()).lower()
                except Exception:
                    key = str(p).lower()
                if key in seen:
                    continue
                seen.add(key)
                paths.append(p)
    paths.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return paths


def _recover_signed_81_same_process(core: SelfHostingFieldOpsCore, state) -> dict[str, Any]:
    if _status(core, state, "chatgpt_worker").get("verified") is True:
        return {"recovered": False, "reason": "already_verified"}

    spec = next(x for x in FIELD_MISSIONS if x.mission == "chatgpt_worker")
    for path in _candidate_result_files():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        row = _extract_child_result(payload)
        if not row or row.get("mission") != "chatgpt_worker":
            continue
        verdict = core.ledger.verify(row, require_windows=False)
        claims = {
            str(item.get("kind"))
            for item in row.get("items", [])
            if str(item.get("value", "")).lower() in {"true", "pass", "verified", "1"}
        }
        missing = sorted(set(spec.required_claims) - claims)
        if not verdict.get("verified") or missing:
            continue
        run_id = str(row.get("run_id") or "")
        if not run_id:
            continue
        bucket = state.metadata.setdefault(core.ledger.KEY, {})
        existing = bucket.get(run_id)
        if existing is not None and existing != row:
            continue
        bucket[run_id] = row
        state.metadata.setdefault("single_process_attestation_recovery_v1", []).append({
            "mission": "chatgpt_worker",
            "run_id": run_id,
            "input": str(path),
            "verification": verdict,
            "recovered_at": datetime.now(timezone.utc).isoformat(),
        })
        state.metadata["single_process_attestation_recovery_v1"] = state.metadata["single_process_attestation_recovery_v1"][-50:]
        after = _status(core, state, "chatgpt_worker")
        if after.get("verified") is True:
            return {
                "recovered": True,
                "reason": "signed_81_imported_in_memory",
                "run_id": run_id,
                "input": str(path),
                "verification": verdict,
            }
    return {"recovered": False, "reason": "no_locally_valid_signed_81_found"}


def _save(store, catalog, state) -> None:
    store.save(state)
    catalog.register(state, make_active=True)


def _fresh_persistence_check(catalog: ProjectCatalog) -> dict[str, Any]:
    fresh_store = catalog.store(PROJECT_ID)
    fresh_state = fresh_store.load()
    if fresh_state is None:
        return {"ok": False, "reason": "canonical_project_missing_after_save"}
    fresh_core = SelfHostingFieldOpsCore()
    statuses = _compact(fresh_core, fresh_state)
    required = ["chatgpt_worker", "chatgpt_multiturn", "self_improvement_field", "alpha_certification"]
    missing = [m for m in required if not statuses[m]["verified"]]
    evidence = fresh_state.metadata.get(fresh_core.ledger.KEY, {})
    counts = {m: sum(1 for row in evidence.values() if isinstance(row, dict) and row.get("mission") == m) for m in required}
    return {
        "ok": not missing,
        "fresh_state_id": fresh_state.id,
        "missing": missing,
        "signed_row_counts": counts,
        "statuses": {m: statuses[m] for m in required},
    }


def _provider_failure(state) -> Any:
    return state.metadata.get("last_ai_field_failure")


def main() -> int:
    if os.name != "nt":
        _write({"status": "NOT_RUN", "reason": "windows_required", "production_verified": False})
        return 2
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        _write({"status": "BLOCKED", "reason": "no_live_ai_provider_configured", "production_verified": False})
        return 3

    try:
        catalog, store, state = _load_canonical()
        core = SelfHostingFieldOpsCore()
        pre = _compact(core, state)
        required = ["windows_read_only", "chrome_navigation", "chrome_session", "download", "multi_app"]
        missing = [m for m in required if not pre[m]["verified"]]
        if missing:
            _write({"status": "BLOCKED", "reason": "pre_ai_field_chain_not_verified", "missing": missing, "statuses": pre, "production_verified": False})
            return 4

        print("=== CEO — AI GATES EN UN SOLO PROCESO ===")
        print("No se repetiran 76-80. No hay subprocess para 81/82.")
        print("Sin auto-promocion, sin Git de red, sin gasto automatico.\n")

        recovery81 = _recover_signed_81_same_process(core, state)
        _save(store, catalog, state)

        row81 = _status(core, state, "chatgpt_worker")
        reran81 = False
        if row81.get("verified") is not True:
            print("[CEO] La attestation previa 81 no pudo reutilizarse; ejecutando 81 en este mismo proceso...")
            result81 = asyncio.run(run_chatgpt_worker(core, state, False))
            reran81 = True
            _save(store, catalog, state)
            row81 = _status(core, state, "chatgpt_worker")
        else:
            result81 = None
            print("[CEO] Mision 81 recuperada y verificada localmente. NO se repite.")

        if row81.get("verified") is not True:
            _write({
                "status": "BLOCKED",
                "reason": "mission_81_not_verified_single_process",
                "recovery_81": recovery81,
                "reran_81": reran81,
                "mission_81_result": result81,
                "provider_failure": _provider_failure(state),
                "statuses": _compact(core, state),
                "production_verified": False,
            })
            return 5

        print("[CEO] Ejecutando mision 82 en el MISMO proceso/estado...")
        row82 = _status(core, state, "chatgpt_multiturn")
        result82 = None
        if row82.get("verified") is not True:
            result82 = asyncio.run(run_chatgpt_worker(core, state, True))
            _save(store, catalog, state)
            row82 = _status(core, state, "chatgpt_multiturn")
        if row82.get("verified") is not True:
            _write({
                "status": "BLOCKED",
                "reason": "mission_82_not_verified_single_process",
                "recovery_81": recovery81,
                "mission_82_result": result82,
                "provider_failure": _provider_failure(state),
                "statuses": _compact(core, state),
                "production_verified": False,
            })
            return 6

        row83 = _status(core, state, "self_improvement_field")
        result83 = None
        if row83.get("verified") is not True:
            print("[CEO] 81/82 verificadas. Reintentando SOLO attestation 83 con evidencia existente...")
            result83 = run_self_improvement_attestation(core, state, ROOT)
            _save(store, catalog, state)
            row83 = _status(core, state, "self_improvement_field")
        if row83.get("verified") is not True:
            _write({
                "status": "PARTIAL",
                "reason": "mission_83_not_verified_after_ai_gates",
                "recovery_81": recovery81,
                "mission_82_result": result82,
                "mission_83_result": result83,
                "statuses": _compact(core, state),
                "production_verified": False,
            })
            return 7

        row84 = _status(core, state, "alpha_certification")
        result84 = None
        if row84.get("verified") is not True:
            print("\n[CEO] 76-83 verificadas. Falta reemitir Alpha (84).")
            answer = input("[CEO] Confirmas que la prueba fisica previa de recovery/resume ya fue realizada? [S/N]: ").strip().lower()
            if answer not in {"s", "si", "sí", "y", "yes"}:
                _write({
                    "status": "PARTIAL",
                    "reason": "alpha_recovery_confirmation_not_granted",
                    "statuses": _compact(core, state),
                    "production_verified": False,
                })
                return 8
            result84 = run_alpha_certification(core, state, True)
            _save(store, catalog, state)
            row84 = _status(core, state, "alpha_certification")

        if row84.get("verified") is not True:
            _write({
                "status": "PARTIAL",
                "reason": "alpha_still_not_verified",
                "mission_84_result": result84,
                "statuses": _compact(core, state),
                "production_verified": False,
            })
            return 9

        # Critical cross-process check: verify the signed chain by re-opening the
        # canonical SQLite store through a new store instance before launching work.
        # This is the condition that previously failed when a stale project row shadowed
        # the newly signed Alpha state.
        persistence = _fresh_persistence_check(catalog)
        if not persistence.get("ok"):
            _write({
                "status": "BLOCKED",
                "reason": "signed_ai_alpha_chain_not_persistent_across_fresh_reload",
                "project_id": PROJECT_ID,
                "mission_81_verified": True,
                "mission_82_verified": True,
                "mission_83_verified": True,
                "alpha_verified_in_memory": True,
                "recovery_81": recovery81,
                "persistence_check": persistence,
                "statuses": _compact(core, state),
                "production_verified": False,
            })
            return 10

        payload = {
            "status": "PASS",
            "project_id": PROJECT_ID,
            "mission_81_verified": True,
            "mission_82_verified": True,
            "mission_83_verified": True,
            "alpha_verified": True,
            "recovery_81": recovery81,
            "persistence_check": persistence,
            "statuses": _compact(core, state),
            "next": "start_work_session_001",
            "production_verified": False,
        }
        _write(payload)

        print("\n[CEO] Cadena 81-84 verificada tambien tras recarga limpia del store. Iniciando Work Session 001...")
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_first_ceo_work_session.py")], cwd=str(ROOT), check=False)
        return int(proc.returncode)
    except Exception as exc:
        _write({
            "status": "FAILED",
            "reason": "single_process_bridge_exception",
            "error": f"{type(exc).__name__}: {exc}",
            "production_verified": False,
        })
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
