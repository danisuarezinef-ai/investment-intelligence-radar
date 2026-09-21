from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ceo_core.installed_runtime_gate_v1 import inspect_installed_runtime_v1
from ceo_core.candidate_admission_seal_v1 import build_candidate_admission_seal_v1
from ceo_core.safe_staging_rehearsal_v2 import safe_staging_rehearsal_v2
from ceo_core.diagnostic_support_bundle_v1 import build_diagnostic_support_bundle_v1

CANDIDATE="1.5.38-rc1-physical-campaign-final-gate"

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--candidate-root",default=str(ROOT));ap.add_argument("--output",default="");ap.add_argument("--allow-nonwindows-test",action="store_true");ns=ap.parse_args()
    cand=Path(ns.candidate_root).resolve();local=Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir());updates=local/"CEO de IAs"/"updates"
    runtime=inspect_installed_runtime_v1(updates,os_name="windows" if ns.allow_nonwindows_test else None)
    seal=build_candidate_admission_seal_v1(cand,expected_version=CANDIDATE,campaign_id="dev261-physical")
    stage=safe_staging_rehearsal_v2(cand,expected_version=CANDIDATE)
    preflight={"ok":False,"detail":"not_run"}
    if seal.get("admitted"):
        with tempfile.TemporaryDirectory(prefix="dev261-win-preflight-") as td:
            cp=subprocess.run([sys.executable,"-u",str(cand/"scripts"/"update_candidate_preflight.py"),"--root",str(cand),"--expected-version",CANDIDATE,"--sandbox-parent",td,"--timeout","25"],cwd=str(cand),capture_output=True,text=True,timeout=45)
            preflight={"ok":cp.returncode==0,"returncode":cp.returncode,"detail":((cp.stdout or "")+(cp.stderr or ""))[-3000:]}
    ready=bool(runtime.get("ok") and seal.get("admitted") and stage.get("ok") and preflight.get("ok"))
    result={"candidate":CANDIDATE,"runtime":runtime,"seal":seal,"staging_rehearsal":stage,"preflight":preflight,"ready_for_human_cutover":ready,"cutover_performed":False,"automatic_installation":False,"human_confirmation_required":True}
    out=Path(ns.output) if ns.output else updates/"DEV261_WINDOWS_PREFLIGHT.json";out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    support=build_diagnostic_support_bundle_v1(out.with_name("DEV261_DIAGNOSTIC_SUPPORT.zip"),evidence=result);result["diagnostic_bundle"]=support
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if ready else 7
if __name__=="__main__":raise SystemExit(main())
