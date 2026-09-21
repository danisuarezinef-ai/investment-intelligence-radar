from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from .in_app_updater import InAppUpdater


def _h(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def run_rollback_preservation_proof_v2() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="dev258-") as td:
        base=Path(td); data=base/"data"; updater=InAppUpdater(data,trusted_keys={})
        projects=data/"projects";projects.mkdir(parents=True); sentinel=projects/"USER_PROJECT.json";sentinel.write_text('{"important":"keep-me"}\n',encoding="utf-8"); before=_h(sentinel)
        prev=base/"prev";prev.mkdir(); launcher=prev/"ABRIR_CEO.cmd";launcher.write_text("@echo off\n",encoding="utf-8")
        cand=base/"cand";cand.mkdir()
        InAppUpdater._atomic_json(updater.previous_path,{"version":"stable","root":str(prev),"launcher":launcher.name,"status":"healthy"})
        InAppUpdater._atomic_json(updater.current_path,{"version":"candidate","root":str(cand),"launcher":"ABRIR_CEO.cmd","status":"pending_health"})
        result=updater.rollback(reason="dev258-proof",failed_version="candidate")
        after=_h(sentinel); current=updater.current_pointer() or {}
        return {"ok":before==after and current.get("version")=="stable","user_project_hash_before":before,"user_project_hash_after":after,"user_data_preserved":before==after,"restored_version":current.get("version"),"rollback":result}
