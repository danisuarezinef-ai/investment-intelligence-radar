from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.core_health_contract_v2 import build_core_health_v2
from ceo_core.dead_update_recovery_v2 import DeadUpdateRecoveryV2
from ceo_core.in_app_updater import InAppUpdater
from ceo_core.release_readiness_v17 import UpdateRecoveryReadinessV17
from ceo_core.rollback_guarantee_v2 import verify_rollback_result_v2
from ceo_core.update_failure_campaign_v2 import UpdateFailureCampaignV2
from ceo_core.update_failure_evidence_v1 import UpdateFailureEvidenceRecorderV1
from ceo_core.update_progress_telemetry_v2 import enrich_update_progress_v2
from ceo_core.update_soak_v2 import UpdateSoakV2
from ceo_core.update_state_audit_v1 import UpdateStateAuditV1

CANDIDATE = "1.5.18-rc1-update-recovery-zero-risk-activation"


def _load_work_mode():
    spec = importlib.util.spec_from_file_location("dev241_work_mode", ROOT / "scripts" / "ceo_stdlib_work_mode.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load work mode")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def dev232_failure_evidence() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev232-") as td:
        rec = UpdateFailureEvidenceRecorderV1(td)
        row = rec.record("health_check", outcome="failed", reason="HTTP 429", api_key="SECRET", path=r"C:\Users\Dani\x")
        latest = json.loads((Path(td) / "update-failure-latest.json").read_text(encoding="utf-8"))
        hist = (Path(td) / "update-failure-history.jsonl").read_text(encoding="utf-8").strip().splitlines()
        ok = row.get("api_key") == "[REDACTED]" and "%USERPROFILE%" in str(row.get("path")) and len(hist) == 1 and latest["phase"] == "health_check"
        return {"ok": ok, "latest": latest}


def dev233_provider_independent_startup() -> dict:
    mod = _load_work_mode()
    old = os.environ.get("CEO_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="dev233-") as td:
        os.environ["CEO_DATA_DIR"] = td
        engine = None
        try:
            start = time.monotonic()
            engine = mod.CEOEngine("AIza" + "x" * 35)
            elapsed = time.monotonic() - start
            ok = elapsed < 10 and engine.execution_enabled is False and engine.provider_validation_in_progress is False and engine._pending_gemini_key is not None
            return {"ok": ok, "constructor_seconds": round(elapsed, 4), "provider_mode": engine.provider_mode, "network_validation_started": engine.provider_validation_in_progress}
        finally:
            if engine is not None:
                try: engine.call(engine.shutdown(), timeout=10)
                except Exception: pass
            if old is None: os.environ.pop("CEO_DATA_DIR", None)
            else: os.environ["CEO_DATA_DIR"] = old


def dev234_split_health() -> dict:
    payload = build_core_health_v2(
        version=CANDIDATE, activation_id="a", storage_ready=True, runtime_ready=True, frontend_ready=True,
        provider_mode="gemini-validation-failed", execution_enabled=False, provider_error="HTTP 429", provider_validation_in_progress=False,
    )
    ok = payload["ok"] is True and payload["activation_health_ok"] is True and payload["provider"]["state"] == "degraded" and payload["provider"]["required_for_activation_health"] is False
    return {"ok": ok, "health": payload}


def dev235_state_audit() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev235-") as td:
        root = Path(td)
        candidate = root / "candidate"; candidate.mkdir()
        prev = root / "prev"; prev.mkdir()
        (root / "current.json").write_text(json.dumps({"status":"pending_health","root":str(candidate),"activated_at_epoch":time.time()-5000}),encoding="utf-8")
        (root / "previous.json").write_text(json.dumps({"status":"healthy","root":str(prev)}),encoding="utf-8")
        (root / "operation.json").write_text(json.dumps({"updated_at_epoch":time.time()-5000}),encoding="utf-8")
        (root / "update.lock").write_text(json.dumps({"created_at_epoch":time.time()-5000}),encoding="utf-8")
        audit=UpdateStateAuditV1(root).inspect(stale_after_seconds=60)
        ok = {"stale_pending_health","stale_operation","stale_lock"}.issubset(set(audit["problems"])) and audit["recommended_action"]=="recover_interrupted_update"
        return {"ok":ok,"audit":audit}


def _make_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def dev236_rollback_and_dev241_e2e() -> dict:
    # Failure path: candidate exits -> automatic rollback to previous healthy pointer.
    with tempfile.TemporaryDirectory(prefix="dev236-") as td:
        data=Path(td)/"data"; updater=InAppUpdater(data, trusted_keys={})
        prev=Path(td)/"prev"; prev.mkdir(); prev_launcher=prev/"ABRIR_CEO.sh"; _make_executable(prev_launcher,"#!/bin/sh\nexit 0\n")
        candidate=Path(td)/"candidate"; (candidate/"scripts").mkdir(parents=True); cand_launcher=candidate/"ABRIR_CEO.sh"; _make_executable(cand_launcher,"#!/bin/sh\nexit 7\n")
        (candidate/"scripts"/"launch_current.py").write_text("raise SystemExit(7)\n",encoding="utf-8")
        (candidate/updater.RECEIPT_NAME).write_text(json.dumps({"version":CANDIDATE}),encoding="utf-8")
        activation="deadbeef"
        InAppUpdater._atomic_json(updater.previous_path,{"version":"1.5.8","root":str(prev),"launcher":prev_launcher.name,"status":"healthy"})
        InAppUpdater._atomic_json(updater.current_path,{"version":CANDIDATE,"root":str(candidate),"launcher":cand_launcher.name,"health_path":"/api/health","activation_id":activation,"status":"pending_health","activated_at_epoch":time.time()})
        spec=importlib.util.spec_from_file_location("dev241_relaunch",ROOT/"scripts"/"relaunch_after_update.py")
        mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod)
        result=mod.supervise_activation(updater=updater,version=CANDIDATE,activation_id=activation,launcher=cand_launcher,fallback_launcher=prev_launcher,health_timeout=1.5)
        current=updater.current_pointer() or {}
        rollback_ok=bool(result.get("rolled_back") and result.get("rollback_guarantee",{}).get("usable_recovery_path") and current.get("version")=="1.5.8")

    # Success path: a minimal candidate exposes the exact activation health contract.
    with tempfile.TemporaryDirectory(prefix="dev241-success-") as td:
        data=Path(td)/"data"; updater=InAppUpdater(data, trusted_keys={})
        candidate=Path(td)/"candidate"; (candidate/"scripts").mkdir(parents=True)
        launcher=candidate/"ABRIR_CEO.sh"; _make_executable(launcher,"#!/bin/sh\nexit 0\n")
        activation="feedface"
        script=f'''from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer\nimport json,pathlib\nclass H(BaseHTTPRequestHandler):\n def log_message(self,*a): pass\n def do_GET(self):\n  b=json.dumps({{"ok":True,"version":{CANDIDATE!r},"activation_id":{activation!r}}}).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)\ns=ThreadingHTTPServer(("127.0.0.1",0),H);url="http://127.0.0.1:%d"%s.server_address[1];pathlib.Path(__file__).resolve().parents[1].joinpath("CEO_REAL_WORK_INTERFACE_STATUS.json").write_text(json.dumps({{"status":"PASS","url":url}}));s.serve_forever()\n'''
        (candidate/"scripts"/"launch_current.py").write_text(script,encoding="utf-8")
        (candidate/updater.RECEIPT_NAME).write_text(json.dumps({"version":CANDIDATE,"installed":False}),encoding="utf-8")
        InAppUpdater._atomic_json(updater.current_path,{"version":CANDIDATE,"root":str(candidate),"launcher":launcher.name,"health_path":"/api/health","activation_id":activation,"status":"pending_health","activated_at_epoch":time.time()})
        spec=importlib.util.spec_from_file_location("dev241_relaunch_success",ROOT/"scripts"/"relaunch_after_update.py")
        mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod)
        success=mod.supervise_activation(updater=updater,version=CANDIDATE,activation_id=activation,launcher=launcher,fallback_launcher=launcher,health_timeout=6)
        pointer=updater.current_pointer() or {}
        success_ok=bool(success.get("ok") and pointer.get("status")=="healthy" and pointer.get("health_confirmed") is True)
        try:
            if success.get("pid"):
                os.kill(int(success["pid"]), signal.SIGTERM)
        except Exception:
            pass
    return {"ok": rollback_ok and success_ok, "rollback_path": rollback_ok, "success_path": success_ok, "failure_result": result, "success_result": success}


def dev237_dead_recovery() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev237-") as td:
        data=Path(td)/"data"; updater=InAppUpdater(data, trusted_keys={})
        prev=Path(td)/"prev"; prev.mkdir(); launch=prev/"ABRIR_CEO.sh"; _make_executable(launch,"#!/bin/sh\nexit 0\n")
        cand=Path(td)/"cand"; cand.mkdir()
        InAppUpdater._atomic_json(updater.previous_path,{"version":"stable","root":str(prev),"launcher":launch.name,"status":"healthy"})
        InAppUpdater._atomic_json(updater.current_path,{"version":"candidate","root":str(cand),"status":"pending_health","activated_at_epoch":time.time()-1000})
        InAppUpdater._atomic_json(updater.operation_path(),{"phase":"activating","updated_at_epoch":time.time()-1000})
        result=DeadUpdateRecoveryV2(updater).recover(stale_after_seconds=0)
        current=updater.current_pointer() or {}
        ok=bool(result["safe"] and current.get("version")=="stable" and not updater.operation_path().exists())
        return {"ok":ok,"result":result}


def dev238_progress() -> dict:
    rows=[enrich_update_progress_v2(p,{}) for p in ("download","verify","stage","preflight","activating","launching_new_version","health_check","healthy")]
    ok=all(r["phase_total"]==10 for r in rows) and rows[-1]["percent"]==100 and rows[-1]["terminal"] is True and all(rows[i]["phase_index"]<=rows[i+1]["phase_index"] for i in range(len(rows)-1))
    return {"ok":ok,"rows":rows}


def package_contract() -> dict:
    row=json.loads((ROOT/"CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
    bad=[]
    if row.get("app_version")!=CANDIDATE: bad.append("version")
    required=row.get("required_paths") or []; hashes=row.get("file_hashes") or {}
    for rel in required:
        p=ROOT/rel
        if not p.is_file(): bad.append("missing:"+rel); continue
        if rel=="CEO_UPDATE_PACKAGE.json": continue
        if hashlib.sha256(p.read_bytes()).hexdigest()!=str(hashes.get(rel) or ""): bad.append("hash:"+rel)
    return {"ok":not bad,"required":len(required),"hashes":len(hashes),"bad":bad[:20]}


def real_preflight() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev241-preflight-") as td:
        cp=subprocess.run([sys.executable,"-u",str(ROOT/"scripts"/"update_candidate_preflight.py"),"--root",str(ROOT),"--expected-version",CANDIDATE,"--sandbox-parent",td,"--timeout","25"],cwd=str(ROOT),capture_output=True,text=True,timeout=40)
        text=(cp.stdout or "")+("\n"+cp.stderr if cp.stderr else "")
        payload={}
        for line in reversed(text.splitlines()):
            try:
                x=json.loads(line)
                if isinstance(x,dict): payload=x; break
            except Exception: pass
        return {"ok":cp.returncode==0 and payload.get("ok") is True,"returncode":cp.returncode,"detail":text[-3000:]}


def main() -> int:
    d232=dev232_failure_evidence(); d233=dev233_provider_independent_startup(); d234=dev234_split_health(); d235=dev235_state_audit()
    d236_241=dev236_rollback_and_dev241_e2e(); d237=dev237_dead_recovery(); d238=dev238_progress()
    campaign=UpdateFailureCampaignV2().run(); soak=UpdateSoakV2().run(transitions=100_000,seed=241); preflight=real_preflight(); contract=package_contract()
    d239=campaign.violations==0 and campaign.provider_faults_do_not_fail_core_health==3
    d240=soak.violations==0 and soak.duplicate_active_versions==0 and soak.stranded_pending_health==0
    d241=bool(d236_241["ok"] and preflight["ok"] and contract["ok"])
    readiness=UpdateRecoveryReadinessV17(
        d232["ok"],d233["ok"],d234["ok"],d235["ok"],d236_241["rollback_path"],d237["ok"],d238["ok"],d239,d240,d241
    )
    out={"candidate":CANDIDATE,"DEV232":d232,"DEV233":d233,"DEV234":d234,"DEV235":d235,"DEV236_DEV241_E2E":d236_241,"DEV237":d237,"DEV238":d238,"DEV239":campaign.to_dict(),"DEV240":soak.to_dict(),"preflight":preflight,"package_contract":contract,"readiness":readiness.to_dict(),"ok":readiness.local_candidate_ready}
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True,default=str))
    return 0 if out["ok"] else 7

if __name__=="__main__":
    raise SystemExit(main())
