from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.physical_campaign_ticket_v1 import build_physical_campaign_ticket_v1, verify_physical_campaign_ticket_v1
from ceo_core.candidate_staleness_guard_v1 import candidate_staleness_guard_v1
from ceo_core.pre_cutover_matrix_v1 import build_pre_cutover_matrix_v1
from ceo_core.atomic_cutover_drill_v1 import run_atomic_cutover_drill_v1
from ceo_core.crash_window_recovery_v1 import run_crash_window_recovery_v1
from ceo_core.dual_activation_gate_v1 import evaluate_dual_activation_gate_v1
from ceo_core.productive_smoke_gate_v1 import run_productive_smoke_gate_v1
from ceo_core.user_state_migration_guard_v1 import capture_user_state_v1, verify_user_state_unchanged_v1
from ceo_core.campaign_exactly_once_guard_v1 import CampaignExactlyOnceGuardV1
from ceo_core.terminal_campaign_model_v1 import TerminalCampaignModelV1
from ceo_core.release_readiness_v20 import TerminalLocalCampaignReadinessV20
from ceo_core.restart_rehearsal_v2 import run_restart_rehearsal_v2

CANDIDATE = "1.5.48-rc1-terminal-local-campaign-gate"


def dev262():
    with tempfile.TemporaryDirectory(prefix="dev262-") as td:
        pkg = Path(td)/"candidate.zip"; pkg.write_bytes(b"candidate-exact")
        baseline = {"current":{"version":"1.5.38","root_exists":True},"read_only":True}
        ticket = build_physical_campaign_ticket_v1(candidate_path=pkg,candidate_version=CANDIDATE,baseline=baseline)
        good = verify_physical_campaign_ticket_v1(ticket,candidate_path=pkg,baseline=baseline)
        pkg.write_bytes(b"tampered")
        bad = verify_physical_campaign_ticket_v1(ticket,candidate_path=pkg,baseline=baseline)
        return {"ok": bool(ticket["ok"] and good["ok"] and not bad["ok"]), "ticket": ticket, "tamper": bad}


def dev263():
    sha = "a"*64
    good = candidate_staleness_guard_v1(current_version="1.5.38-rc1-x",candidate_version=CANDIDATE,expected_sha256=sha,actual_sha256=sha,current_release_sequence=261,candidate_release_sequence=271)
    stale = candidate_staleness_guard_v1(current_version=CANDIDATE,candidate_version="1.5.38-rc1-x",expected_sha256=sha,actual_sha256=sha,current_release_sequence=271,candidate_release_sequence=270)
    wrong = candidate_staleness_guard_v1(current_version="1.5.38",candidate_version=CANDIDATE,expected_sha256=sha,actual_sha256="b"*64)
    return {"ok": bool(good["ok"] and not stale["ok"] and stale["downgrade_blocked"] and stale["stale_sequence_blocked"] and not wrong["ok"]),"good":good,"stale":stale,"wrong_hash":wrong}


def dev264():
    checks={k:True for k in ("runtime_gate","candidate_identity","admission_seal","isolated_staging","isolated_preflight","recovery_point","core_health","productive_smoke")}
    degraded=build_pre_cutover_matrix_v1(checks,provider_available=False)
    checks["productive_smoke"]=False
    blocked=build_pre_cutover_matrix_v1(checks,provider_available=True)
    return {"ok": bool(degraded["ready_for_human_cutover"] and degraded["provider_is_activation_gate"] is False and not blocked["ready_for_human_cutover"] and "productive_smoke" in blocked["blocking_failures"]),"provider_degraded":degraded,"productive_block":blocked}


def dev265():
    row=run_atomic_cutover_drill_v1(version=CANDIDATE)
    return {"ok":bool(row["ok"] and row["duplicate_activation_blocked"] and row["rollback_restored_version"]=="stable"),"drill":row}


def dev266():
    row=run_crash_window_recovery_v1(version=CANDIDATE)
    return {"ok":bool(row["ok"] and row["pending_health_recovered"] and row["healthy_candidate_preserved"]),"recovery":row}


def _supervisor():
    spec=importlib.util.spec_from_file_location("dev271_relaunch",ROOT/"scripts"/"relaunch_after_update.py")
    mod=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(mod); return mod.supervise_activation


def dev267():
    smoke=run_productive_smoke_gate_v1()
    good=evaluate_dual_activation_gate_v1(core_health={"ok":True},productive_smoke=smoke,provider_status={"ok":False})
    bad=evaluate_dual_activation_gate_v1(core_health={"ok":True},productive_smoke={"ok":False},provider_status={"ok":True})
    rehearsal=run_restart_rehearsal_v2(version=CANDIDATE,supervise_activation=_supervisor())
    success=rehearsal.get("success") or {}
    try:
        if success.get("pid"): os.kill(int(success["pid"]), signal.SIGTERM)
    except Exception: pass
    return {"ok": bool(good["commit_activation"] and not good["provider_required"] and bad["rollback_required"] and rehearsal["ok"] and (success.get("productive_smoke") or {}).get("ok")),"gate":good,"failed_productive":bad,"restart_rehearsal":rehearsal}


def dev268():
    with tempfile.TemporaryDirectory(prefix="dev268-") as td:
        root=Path(td)/"projects"; root.mkdir(); (root/"project.json").write_text('{"goal":"keep me"}\n',encoding="utf-8"); (root/"note.txt").write_text("user data\n",encoding="utf-8")
        before=capture_user_state_v1(root)
        good=verify_user_state_unchanged_v1(before,root)
        (root/"note.txt").write_text("mutated\n",encoding="utf-8")
        bad=verify_user_state_unchanged_v1(before,root)
        return {"ok":bool(good["ok"] and good["user_state_preserved"] and not bad["ok"] and not good["automatic_migration_allowed"]),"unchanged":good,"mutation_detected":bad}


def dev269():
    with tempfile.TemporaryDirectory(prefix="dev269-") as td:
        g=CampaignExactlyOnceGuardV1(Path(td)/"once.json")
        first=g.claim(campaign_id="camp",candidate_sha256="a"*64); token=first["record"]["token"]
        dup=g.claim(campaign_id="camp",candidate_sha256="a"*64)
        conflict=g.claim(campaign_id="other",candidate_sha256="b"*64)
        cut1=g.record_cutover(token=token); cut2=g.record_cutover(token=token)
        return {"ok":bool(first["claimed"] and dup["duplicate"] and conflict["conflict"] and cut1["performed"] and cut2["duplicate_blocked"] and cut2["cutover_count"]==1),"first":first,"duplicate":dup,"conflict":conflict,"cutover1":cut1,"cutover2":cut2}


def dev270():
    row=TerminalCampaignModelV1().run(rounds=1_000_000,seed=271).to_dict()
    return {"ok":bool(row["violations"]==0 and row["unauthorized_cutovers"]==0 and row["lost_stable_rollback_targets"]==0 and row["stranded_pending_health"]==0 and row["user_state_mutations"]==0),"model":row}


def package_contract():
    row=json.loads((ROOT/"CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8")); bad=[]
    if row.get("app_version")!=CANDIDATE: bad.append("version")
    for rel in row.get("required_paths") or []:
        p=ROOT/rel
        if not p.is_file(): bad.append("missing:"+rel); continue
        if rel=="CEO_UPDATE_PACKAGE.json": continue
        if hashlib.sha256(p.read_bytes()).hexdigest()!=str((row.get("file_hashes") or {}).get(rel) or ""): bad.append("hash:"+rel)
    return {"ok":not bad,"required":len(row.get("required_paths") or []),"hashes":len(row.get("file_hashes") or {}),"bad":bad[:30]}


def real_preflight():
    with tempfile.TemporaryDirectory(prefix="dev271-preflight-") as td:
        cp=subprocess.run([sys.executable,"-u",str(ROOT/"scripts"/"update_candidate_preflight.py"),"--root",str(ROOT),"--expected-version",CANDIDATE,"--sandbox-parent",td,"--timeout","25"],cwd=str(ROOT),capture_output=True,text=True,timeout=45)
        text=(cp.stdout or "")+("\n"+cp.stderr if cp.stderr else "")
        return {"ok":cp.returncode==0,"returncode":cp.returncode,"detail":text[-2500:]}


def main()->int:
    d262=dev262();d263=dev263();d264=dev264();d265=dev265();d266=dev266();d267=dev267();d268=dev268();d269=dev269();d270=dev270();contract=package_contract();preflight=real_preflight()
    d271=bool(contract["ok"] and preflight["ok"])
    readiness=TerminalLocalCampaignReadinessV20(d262["ok"],d263["ok"],d264["ok"],d265["ok"],d266["ok"],d267["ok"],d268["ok"],d269["ok"],d270["ok"],d271)
    out={"candidate":CANDIDATE,"DEV262":d262,"DEV263":d263,"DEV264":d264,"DEV265":d265,"DEV266":d266,"DEV267":d267,"DEV268":d268,"DEV269":d269,"DEV270":d270,"DEV271":{"ok":d271,"package_contract":contract,"preflight":preflight},"readiness":readiness.to_dict(),"ok":readiness.to_dict()["local_candidate_ready"]}
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True,default=str)); return 0 if out["ok"] else 7

if __name__=="__main__": raise SystemExit(main())
