from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_field import FIELD_MISSIONS, SelfHostingFieldOpsCore

PROJECT_ID = "windows-self-hosting-field"
DESKTOP = Path.home() / "Desktop"
RESULT_NAME = "CEO_PROJECT_STORE_REPAIR_RESULT.json"
LOCAL_RESULTS = ROOT / "RESULTADOS_CEO"


def _status(core: SelfHostingFieldOpsCore, state, mission: str) -> dict[str, Any]:
    spec = next(x for x in FIELD_MISSIONS if x.mission == mission)
    return core.missions.status(state, spec)


def _rows(db: Path) -> list[dict[str, Any]]:
    if not db.exists():
        return []
    uri = f"file:{db.as_posix()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5) as con:
            result=[]
            for rowid, pid, payload in con.execute("SELECT rowid,id,payload FROM project ORDER BY rowid"):
                alpha=None
                try:
                    data=json.loads(payload)
                    meta=data.get("metadata") or {}
                    evidence=meta.get("self_hosting_field_evidence_v1") or {}
                    alpha=sum(1 for r in evidence.values() if isinstance(r,dict) and r.get("mission")=="alpha_certification")
                except Exception:
                    pass
                result.append({"rowid": int(rowid), "id": str(pid), "alpha_rows": alpha})
            return result
    except Exception as exc:
        return [{"error": f"{type(exc).__name__}: {exc}"}]


def _write(payload: dict[str, Any]) -> None:
    text=json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    for path in [DESKTOP/RESULT_NAME, LOCAL_RESULTS/RESULT_NAME]:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except Exception:
            pass
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    print(f"\n[CEO] Resultado: {DESKTOP/RESULT_NAME}")
    print(f"[CEO] Copia local: {LOCAL_RESULTS/RESULT_NAME}")


def main() -> int:
    if os.name != "nt":
        _write({"status":"NOT_RUN","reason":"windows_required","production_verified":False})
        return 2
    root=user_data_root()
    catalog=ProjectCatalog(root/"projects")
    db=catalog.store_path(PROJECT_ID)
    before_rows=_rows(db)
    store=catalog.store(PROJECT_ID)
    state=store.load()
    if state is None:
        _write({"status":"BLOCKED","reason":"canonical_project_missing","db":str(db),"rows_before":before_rows,"production_verified":False})
        return 3
    loaded_id=state.id
    if state.id != PROJECT_ID:
        state.metadata.setdefault("project_identity_recovery_v1", []).append({
            "from": state.id,
            "to": PROJECT_ID,
            "reason": "shadowed_project_store_repair",
        })
        state.metadata["project_identity_recovery_v1"] = state.metadata["project_identity_recovery_v1"][-50:]
        state.id=PROJECT_ID
    core=SelfHostingFieldOpsCore()
    alpha_before=_status(core,state,"alpha_certification")
    # Saving with the fixed store implementation collapses stale alias rows but never
    # fabricates or rewrites signed evidence rows.
    store.save(state)
    catalog.register(state, make_active=True)
    reloaded=store.load()
    alpha_after=_status(core,reloaded,"alpha_certification") if reloaded else {"verified":False,"status":"MISSING"}
    after_rows=_rows(db)
    payload={
        "status":"PASS" if alpha_after.get("verified") is True else "PARTIAL",
        "project_id":PROJECT_ID,
        "db":str(db),
        "loaded_id_before_repair":loaded_id,
        "rows_before":before_rows,
        "rows_after":after_rows,
        "alpha_before":{"status":alpha_before.get("status"),"verified":bool(alpha_before.get("verified")),"attestation":alpha_before.get("attestation")},
        "alpha_after":{"status":alpha_after.get("status"),"verified":bool(alpha_after.get("verified")),"attestation":alpha_after.get("attestation")},
        "production_verified":False,
        "next":"start_work_session_001" if alpha_after.get("verified") is True else "do_not_bypass_alpha; inspect canonical row evidence",
    }
    _write(payload)
    if alpha_after.get("verified") is not True:
        return 4
    print("\n[CEO] Store canónico reparado y Alpha firmada verificada. Iniciando Work Session 001...")
    proc=subprocess.run([sys.executable, str(ROOT/"scripts"/"run_first_ceo_work_session.py")], cwd=str(ROOT), check=False)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
