from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.campaign_baseline_snapshot_v2 import CampaignBaselineSnapshotV2
from ceo_core.candidate_identity_lock_v1 import CandidateIdentityLockV1
from ceo_core.campaign_checkpoint_v2 import CampaignCheckpointV2
from ceo_core.pre_cutover_recovery_point_v1 import PreCutoverRecoveryPointV1
from ceo_core.startup_watchdog_v3 import StartupWatchdogV3
from ceo_core.update_root_cause_triage_v1 import UpdateRootCauseTriageV1
from ceo_core.productive_smoke_gate_v1 import run_productive_smoke_gate_v1
from ceo_core.one_shot_windows_campaign_executor_v1 import OneShotWindowsCampaignExecutorV1
from ceo_core.physical_campaign_soak_v1 import PhysicalCampaignSoakV1
from ceo_core.release_readiness_v18 import OneShotCampaignReadinessV18
from ceo_core.in_app_updater import InAppUpdater

CANDIDATE = "1.5.28-rc1-one-shot-windows-campaign"


def _atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dev242_baseline() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev242-") as td:
        root = Path(td)
        active = root / "active"; active.mkdir()
        (active / "ABRIR_CEO.cmd").write_text("@echo off\n", encoding="utf-8")
        (active / ".ceo-update-receipt.json").write_text('{"version":"old"}', encoding="utf-8")
        _atomic(root / "current.json", {"version":"old","root":str(active),"launcher":"ABRIR_CEO.cmd","status":"healthy"})
        row = CampaignBaselineSnapshotV2(root).capture()
        return {"ok": bool(row["read_only"] and row["current"]["root_exists"] and row["current"]["launcher_exists"] and len(row["snapshot_sha256"]) == 64), "snapshot": row}


def dev243_identity() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev243-") as td:
        root = Path(td); pkg = root / "candidate.zip"; pkg.write_bytes(b"exact-candidate")
        lock = CandidateIdentityLockV1(root / "lock.json")
        made = lock.create(package_path=pkg, version=CANDIDATE, campaign_id="camp")
        good = lock.verify(pkg, expected_version=CANDIDATE, campaign_id="camp")
        pkg.write_bytes(b"tampered")
        bad = lock.verify(pkg, expected_version=CANDIDATE, campaign_id="camp")
        return {"ok": bool(good["ok"] and not bad["ok"] and ("sha256_mismatch" in bad["problems"] or "size_mismatch" in bad["problems"])), "lock": made, "tamper": bad}


def dev244_checkpoint() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev244-") as td:
        cp = CampaignCheckpointV2(Path(td)/"cp.json", campaign_id="camp")
        cp.record("baseline"); cp.record("identity_lock"); cp.record("recovery_point")
        order_blocked = False
        try: cp.record("preflight")
        except RuntimeError: order_blocked = True
        state = cp.resumable_state()
        return {"ok": bool(order_blocked and state["next_phase"] == "stage" and state["passed"] == ["baseline","identity_lock","recovery_point"]), "state": state, "order_violation_blocked": order_blocked}


def dev245_recovery() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev245-") as td:
        root = Path(td); active = root / "active"; active.mkdir()
        _atomic(root/"current.json", {"version":"old","root":str(active),"status":"healthy"})
        _atomic(root/"previous.json", {"version":"older","root":str(active),"status":"healthy"})
        mgr = PreCutoverRecoveryPointV1(root); made = mgr.create(campaign_id="camp"); verified = mgr.verify("camp")
        return {"ok": bool(made["restorable"] and made["project_data_touched"] is False and verified["ok"]), "recovery": made, "verify": verified}


def dev246_watchdog() -> dict:
    wd = StartupWatchdogV3(deadline_seconds=5)
    waiting = wd.observe(process_alive=True)
    healthy = wd.observe(process_alive=True, status_url_seen=True, health_confirmed=True)
    wd2 = StartupWatchdogV3(deadline_seconds=5); wd2.started -= 6
    timeout = wd2.observe(process_alive=True, reason="provider HTTP 429")
    return {"ok": bool(waiting.state=="WAITING" and healthy.state=="HEALTHY" and timeout.state=="CORE_HEALTH_TIMEOUT" and timeout.provider_required is False), "waiting":waiting.to_dict(),"healthy":healthy.to_dict(),"timeout":timeout.to_dict()}


def dev247_triage() -> dict:
    t = UpdateRootCauseTriageV1()
    provider = t.classify({"phase":"health_check","reason":"Gemini HTTP 429 quota"})
    core = t.classify({"phase":"health_check","reason":"core_health_timeout after 45s"})
    identity = t.classify({"phase":"verify","reason":"sha256_mismatch"})
    return {"ok": bool(provider["category"]=="provider_degraded" and provider["core_should_remain_healthy"] and core["category"]=="core_startup" and identity["category"]=="candidate_identity" and not provider["automatic_patch_chain"]), "provider":provider,"core":core,"identity":identity}


def dev248_smoke() -> dict:
    row = run_productive_smoke_gate_v1()
    return {"ok": bool(row["ok"] and not row["external_provider_used"] and row["spending_attempts"]==0), "smoke": row}


def dev249_executor() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev249-") as td:
        root = Path(td)/"updates"; root.mkdir(parents=True)
        active = root/"active"; active.mkdir(); (active/"ABRIR_CEO.cmd").write_text("@echo off\n",encoding="utf-8")
        _atomic(root/"current.json", {"version":"old","root":str(active),"launcher":"ABRIR_CEO.cmd","status":"healthy"})
        pkg=Path(td)/"candidate.zip";pkg.write_bytes(b"candidate-one-shot")
        ex=OneShotWindowsCampaignExecutorV1(updates_root=root,package_path=pkg,version=CANDIDATE)
        prep=ex.prepare(); no=ex.authorize_cutover(confirmation="yes")
        sha=prep["identity_lock"]["sha256"]
        yes=ex.authorize_cutover(confirmation=f"ACTIVATE {ex.campaign_id} {sha}")
        snap=ex.snapshot()
        return {"ok": bool(prep["ready_for_stage"] and not prep["cutover_authorized"] and not no["authorized"] and yes["authorized"] and snap["identity"]["ok"]), "prepare":prep,"wrong_confirmation":no,"explicit_confirmation":yes,"snapshot":snap}


def package_contract() -> dict:
    row=json.loads((ROOT/"CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
    bad=[]; hashes=row.get("file_hashes") or {}; required=row.get("required_paths") or []
    if row.get("app_version") != CANDIDATE: bad.append("version")
    for rel in required:
        p=ROOT/rel
        if not p.is_file(): bad.append("missing:"+rel); continue
        if rel=="CEO_UPDATE_PACKAGE.json": continue
        got=hashlib.sha256(p.read_bytes()).hexdigest()
        if got != str(hashes.get(rel) or ""): bad.append("hash:"+rel)
    return {"ok":not bad,"required":len(required),"hashes":len(hashes),"bad":bad[:20]}


def real_preflight() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev251-preflight-") as td:
        cp=subprocess.run([sys.executable,"-u",str(ROOT/"scripts"/"update_candidate_preflight.py"),"--root",str(ROOT),"--expected-version",CANDIDATE,"--sandbox-parent",td,"--timeout","25"],cwd=str(ROOT),capture_output=True,text=True,timeout=45)
        text=(cp.stdout or "")+("\n"+cp.stderr if cp.stderr else "")
        payload={}
        for line in reversed(text.splitlines()):
            try:
                x=json.loads(line)
                if isinstance(x,dict): payload=x; break
            except Exception: pass
        return {"ok":cp.returncode==0 and payload.get("ok") is True,"returncode":cp.returncode,"detail":text[-2500:]}


def dev250_soak() -> dict:
    report=PhysicalCampaignSoakV1().run(rounds=100_000,seed=251)
    return {"ok": report.violations==0 and report.unauthorized_cutovers==0 and report.stranded_campaigns==0, "soak":report.to_dict()}


def supervisor_regression() -> dict:
    spec=importlib.util.spec_from_file_location("dev251_relaunch",ROOT/"scripts"/"relaunch_after_update.py")
    mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory(prefix="dev251-supervisor-") as td:
        data=Path(td)/"data"; updater=InAppUpdater(data,trusted_keys={})
        prev=Path(td)/"prev";prev.mkdir();pl=prev/"ABRIR_CEO.sh";pl.write_text("#!/bin/sh\nexit 0\n",encoding="utf-8");pl.chmod(pl.stat().st_mode|stat.S_IXUSR)
        cand=Path(td)/"cand";(cand/"scripts").mkdir(parents=True);cl=cand/"ABRIR_CEO.sh";cl.write_text("#!/bin/sh\nexit 7\n",encoding="utf-8");cl.chmod(cl.stat().st_mode|stat.S_IXUSR)
        (cand/"scripts"/"launch_current.py").write_text("raise SystemExit(7)\n",encoding="utf-8")
        (cand/updater.RECEIPT_NAME).write_text(json.dumps({"version":CANDIDATE}),encoding="utf-8")
        activation="deadbeef"
        InAppUpdater._atomic_json(updater.previous_path,{"version":"old","root":str(prev),"launcher":pl.name,"status":"healthy"})
        InAppUpdater._atomic_json(updater.current_path,{"version":CANDIDATE,"root":str(cand),"launcher":cl.name,"health_path":"/api/health","activation_id":activation,"status":"pending_health","activated_at_epoch":time.time()})
        result=mod.supervise_activation(updater=updater,version=CANDIDATE,activation_id=activation,launcher=cl,fallback_launcher=pl,health_timeout=1.0)
        return {"ok": bool(result.get("rolled_back") and result.get("triage",{}).get("category")=="core_startup" and result.get("watchdog",{}).get("provider_required") is False), "result":result}


def main()->int:
    d242=dev242_baseline(); d243=dev243_identity(); d244=dev244_checkpoint(); d245=dev245_recovery(); d246=dev246_watchdog(); d247=dev247_triage(); d248=dev248_smoke(); d249=dev249_executor(); d250=dev250_soak(); sup=supervisor_regression(); contract=package_contract(); preflight=real_preflight()
    d251=bool(contract["ok"] and preflight["ok"] and sup["ok"])
    ready=OneShotCampaignReadinessV18(d242["ok"],d243["ok"],d244["ok"],d245["ok"],d246["ok"],d247["ok"],d248["ok"],d249["ok"],d250["ok"],d251)
    out={"candidate":CANDIDATE,"DEV242":d242,"DEV243":d243,"DEV244":d244,"DEV245":d245,"DEV246":d246,"DEV247":d247,"DEV248":d248,"DEV249":d249,"DEV250":d250,"DEV251":{"ok":d251,"package_contract":contract,"preflight":preflight,"supervisor_regression":sup},"readiness":ready.to_dict(),"ok":ready.local_candidate_ready}
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True,default=str))
    return 0 if out["ok"] else 7

if __name__=="__main__": raise SystemExit(main())
