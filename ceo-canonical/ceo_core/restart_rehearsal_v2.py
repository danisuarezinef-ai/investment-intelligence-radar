from __future__ import annotations

import json
import os
import signal
import stat
import tempfile
import time
from pathlib import Path
from typing import Any

from .in_app_updater import InAppUpdater


def _exec(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_restart_rehearsal_v2(*, version: str, supervise_activation) -> dict[str, Any]:
    """Exercise both success and rollback restart paths using local child processes."""
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="ceo-restart-v2-fail-") as td:
        data = Path(td) / "data"; updater = InAppUpdater(data, trusted_keys={})
        prev = Path(td) / "prev"; prev.mkdir(); pl = prev / "ABRIR_CEO.sh"; _exec(pl, "#!/bin/sh\nexit 0\n")
        cand = Path(td) / "cand"; (cand / "scripts").mkdir(parents=True); cl = cand / "ABRIR_CEO.sh"; _exec(cl, "#!/bin/sh\nexit 9\n")
        (cand / "scripts" / "launch_current.py").write_text("raise SystemExit(9)\n", encoding="utf-8")
        (cand / updater.RECEIPT_NAME).write_text(json.dumps({"version":version}), encoding="utf-8")
        aid = "dev256fail"
        InAppUpdater._atomic_json(updater.previous_path, {"version":"stable","root":str(prev),"launcher":pl.name,"status":"healthy"})
        InAppUpdater._atomic_json(updater.current_path, {"version":version,"root":str(cand),"launcher":cl.name,"activation_id":aid,"status":"pending_health","health_path":"/api/health","activated_at_epoch":time.time()})
        fail = supervise_activation(updater=updater, version=version, activation_id=aid, launcher=cl, fallback_launcher=pl, health_timeout=1.0)
        results["rollback"] = fail
    with tempfile.TemporaryDirectory(prefix="ceo-restart-v2-ok-") as td:
        data = Path(td) / "data"; updater = InAppUpdater(data, trusted_keys={})
        cand = Path(td) / "cand"; (cand / "scripts").mkdir(parents=True); cl = cand / "ABRIR_CEO.sh"; _exec(cl, "#!/bin/sh\nexit 0\n")
        aid = "dev256ok"
        script = f'''from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer\nimport json,pathlib\nclass H(BaseHTTPRequestHandler):\n def log_message(self,*a): pass\n def do_GET(self):\n  b=json.dumps({{"ok":True,"version":{version!r},"activation_id":{aid!r},"provider":{{"state":"degraded","required_for_activation_health":False}}}}).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)\ns=ThreadingHTTPServer(("127.0.0.1",0),H);u="http://127.0.0.1:%d"%s.server_address[1];pathlib.Path(__file__).resolve().parents[1].joinpath("CEO_REAL_WORK_INTERFACE_STATUS.json").write_text(json.dumps({{"status":"PASS","url":u}}));s.serve_forever()\n'''
        (cand / "scripts" / "launch_current.py").write_text(script, encoding="utf-8")
        (cand / updater.RECEIPT_NAME).write_text(json.dumps({"version":version}), encoding="utf-8")
        InAppUpdater._atomic_json(updater.current_path, {"version":version,"root":str(cand),"launcher":cl.name,"activation_id":aid,"status":"pending_health","health_path":"/api/health","activated_at_epoch":time.time()})
        ok = supervise_activation(updater=updater, version=version, activation_id=aid, launcher=cl, fallback_launcher=cl, health_timeout=5.0)
        results["success"] = ok
        try:
            if ok.get("pid"): os.kill(int(ok["pid"]), signal.SIGTERM)
        except Exception: pass
    return {"ok": bool(results["rollback"].get("rolled_back") and results["success"].get("ok")), **results}
