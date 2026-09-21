from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from ceo_core.installed_runtime_gate_v1 import inspect_installed_runtime_v1
from ceo_core.candidate_admission_seal_v1 import build_candidate_admission_seal_v1
from ceo_core.campaign_evidence_chain_v1 import CampaignEvidenceChainV1
from ceo_core.safe_staging_rehearsal_v2 import safe_staging_rehearsal_v2
from ceo_core.restart_rehearsal_v2 import run_restart_rehearsal_v2
from ceo_core.productive_continuity_gate_v2 import run_productive_continuity_gate_v2
from ceo_core.rollback_preservation_proof_v2 import run_rollback_preservation_proof_v2
from ceo_core.diagnostic_support_bundle_v1 import build_diagnostic_support_bundle_v1
from ceo_core.physical_campaign_chaos_v2 import PhysicalCampaignChaosV2
from ceo_core.release_readiness_v19 import PhysicalCampaignReadinessV19

CANDIDATE="1.5.38-rc1-physical-campaign-final-gate"

def _atomic(path:Path,payload:dict): path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def dev252():
    with tempfile.TemporaryDirectory(prefix="dev252-") as td:
        root=Path(td);active=root/"active";active.mkdir();(active/"ABRIR_CEO.cmd").write_text("@echo off\n",encoding="utf-8")
        _atomic(root/"current.json",{"version":"1.5.28","root":str(active),"launcher":"ABRIR_CEO.cmd","status":"healthy"})
        row=inspect_installed_runtime_v1(root,os_name="windows",architecture="AMD64",python_version=(3,13),free_bytes=2_000_000_000)
        low=inspect_installed_runtime_v1(root,os_name="windows",architecture="AMD64",python_version=(3,13),free_bytes=1)
        return {"ok":bool(row["ok"] and row["read_only"] and not low["ok"] and "insufficient_free_space" in low["problems"]),"runtime":row,"low_space":low}

def dev253():
    row=build_candidate_admission_seal_v1(ROOT,expected_version=CANDIDATE,campaign_id="dev261-campaign")
    return {"ok":bool(row["admitted"] and len(row["seal_sha256"])==64 and row["hashes_verified"]>=1),"seal":row}

def dev254():
    with tempfile.TemporaryDirectory(prefix="dev254-") as td:
        path=Path(td)/"chain.json";chain=CampaignEvidenceChainV1(path)
        chain.append("baseline",{"sha256":"a"*64});chain.append("candidate",{"sha256":"b"*64});chain.append("preflight",{"ok":True})
        good=chain.verify(); data=json.loads(path.read_text(encoding="utf-8"));data[1]["payload"]["sha256"]="x"*64;path.write_text(json.dumps(data),encoding="utf-8")
        bad=CampaignEvidenceChainV1(path).verify()
        return {"ok":bool(good["ok"] and good["records"]==3 and not bad["ok"]),"verified":good,"tamper_detected":not bad["ok"]}

def dev255():
    row=safe_staging_rehearsal_v2(ROOT,expected_version=CANDIDATE)
    return {"ok":bool(row["ok"] and row["isolated"] and not row["activation_attempted"] and not row["active_pointer_changed"]),"staging":row}

def _supervisor():
    spec=importlib.util.spec_from_file_location("dev261_relaunch",ROOT/"scripts"/"relaunch_after_update.py")
    mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod);return mod.supervise_activation

def dev256():
    row=run_restart_rehearsal_v2(version=CANDIDATE,supervise_activation=_supervisor())
    return {"ok":bool(row["ok"] and row["rollback"].get("rolled_back") and row["success"].get("ok")),"rehearsal":row}

def dev257():
    row=run_productive_continuity_gate_v2();return {"ok":bool(row["ok"] and row["completed"]==12 and row["restart_resume"] and row["spending_attempts"]==0),"continuity":row}

def dev258():
    row=run_rollback_preservation_proof_v2();return {"ok":bool(row["ok"] and row["user_data_preserved"] and row["restored_version"]=="stable"),"preservation":row}

def dev259():
    with tempfile.TemporaryDirectory(prefix="dev259-") as td:
        row=build_diagnostic_support_bundle_v1(Path(td)/"support.zip",evidence={"phase":"rollback","api_key":"AIza"+"x"*35,"nested":{"authorization":"Bearer secret"},"reason":"Gemini HTTP 429","project_summary":"metadata only"})
        return {"ok":bool(row["ok"] and not row["secret_leak_detected"] and not row["user_project_contents_included"]),"bundle":row}

def dev260():
    row=PhysicalCampaignChaosV2().run(rounds=250_000,seed=261).to_dict();return {"ok":bool(row["violations"]==0 and row["unauthorized_cutovers"]==0 and row["stranded_campaigns"]==0 and row["user_data_mutations"]==0),"chaos":row}

def package_contract():
    row=json.loads((ROOT/"CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"));bad=[]
    if row.get("app_version")!=CANDIDATE:bad.append("version")
    for rel in row.get("required_paths") or []:
        p=ROOT/rel
        if not p.is_file():bad.append("missing:"+rel);continue
        if rel=="CEO_UPDATE_PACKAGE.json":continue
        if hashlib.sha256(p.read_bytes()).hexdigest()!=str((row.get("file_hashes") or {}).get(rel) or ""):bad.append("hash:"+rel)
    return {"ok":not bad,"required":len(row.get("required_paths") or []),"hashes":len(row.get("file_hashes") or {}),"bad":bad[:30]}

def real_preflight():
    with tempfile.TemporaryDirectory(prefix="dev261-preflight-") as td:
        cp=subprocess.run([sys.executable,"-u",str(ROOT/"scripts"/"update_candidate_preflight.py"),"--root",str(ROOT),"--expected-version",CANDIDATE,"--sandbox-parent",td,"--timeout","25"],cwd=str(ROOT),capture_output=True,text=True,timeout=45)
        text=(cp.stdout or "")+("\n"+cp.stderr if cp.stderr else "");payload={}
        for line in reversed(text.splitlines()):
            try:
                x=json.loads(line)
                if isinstance(x,dict):payload=x;break
            except Exception:pass
        return {"ok":cp.returncode==0 and payload.get("ok") is True,"returncode":cp.returncode,"payload":payload,"detail":text[-1500:]}

def main()->int:
    d252=dev252();d253=dev253();d254=dev254();d255=dev255();d256=dev256();d257=dev257();d258=dev258();d259=dev259();d260=dev260();contract=package_contract();preflight=real_preflight()
    d261=bool(contract["ok"] and preflight["ok"])
    readiness=PhysicalCampaignReadinessV19(d252["ok"],d253["ok"],d254["ok"],d255["ok"],d256["ok"],d257["ok"],d258["ok"],d259["ok"],d260["ok"],d261)
    out={"candidate":CANDIDATE,"DEV252":d252,"DEV253":d253,"DEV254":d254,"DEV255":d255,"DEV256":d256,"DEV257":d257,"DEV258":d258,"DEV259":d259,"DEV260":d260,"DEV261":{"ok":d261,"package_contract":contract,"preflight":preflight},"readiness":readiness.to_dict(),"ok":readiness.to_dict()["local_candidate_ready"]}
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True,default=str));return 0 if out["ok"] else 7

if __name__=="__main__":raise SystemExit(main())
