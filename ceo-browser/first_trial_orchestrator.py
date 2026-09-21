from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from first_trial_safety import (
    atomic_json,
    bounded_text,
    go_criteria,
    local_root if False else None,
    run_preflight,
)


def local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def read_json(path: Path) -> dict:
    row=json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(row,dict):
        raise ValueError(f"{path.name}: expected object")
    return row


def run_powershell(script: Path, *, profile_dir: Path, port: int, timeout: int) -> tuple[int,str]:
    cmd=[
        "powershell.exe" if os.name=="nt" else "pwsh",
        "-NoProfile","-ExecutionPolicy","Bypass","-File",str(script),
        "-ProfileDir",str(profile_dir),
        "-Port",str(port),
        "-TimeoutSeconds",str(timeout),
    ]
    proc=subprocess.run(cmd,capture_output=True,text=True,timeout=max(600,timeout*8))
    output=((proc.stdout or "")+"\n"+(proc.stderr or "")).strip()
    return proc.returncode,bounded_text(output)


def main() -> int:
    parser=argparse.ArgumentParser()
    base=Path(__file__).resolve().parent
    local=local_appdata()
    parser.add_argument("--profile-dir",default=str(local/"CEO de IAs"/"browser-profile"))
    parser.add_argument("--evidence-dir",default=str(local/"CEO de IAs"/"evidence"))
    parser.add_argument("--preferred-port",type=int,default=9227)
    parser.add_argument("--timeout",type=int,default=180)
    parser.add_argument("--preflight-only",action="store_true")
    args=parser.parse_args()

    profile=Path(args.profile_dir).expanduser().resolve()
    evidence=Path(args.evidence_dir).expanduser().resolve()
    evidence.mkdir(parents=True,exist_ok=True)

    report=run_preflight(
        browser_ai_dir=base,
        profile_dir=profile,
        evidence_dir=evidence,
        preferred_port=args.preferred_port,
    )
    consolidated={
        "schema_version":1,
        "created_at_epoch":int(time.time()),
        "trial_id":report.trial_id,
        "stage":"PREFLIGHT",
        "preflight_status":report.status,
        "selected_cdp_port":report.selected_cdp_port,
        "field_gate_status":"NOT_RUN",
        "BROWSER_FIELD_VERIFIED":False,
        "first_autodevelopment_launch_allowed":False,
        "api_calls_required":0,
        "production_promotion_allowed":False,
        "automatic_merge_allowed":False,
        "automatic_purchase_allowed":False,
        "b38_automatically_started":False,
        "evidence":{
            "preflight":str(evidence/"FIRST_TRIAL_PREFLIGHT.json"),
            "field_state":str(evidence/"BROWSER_FIELD_STATE.json"),
        },
        "failure_reason":"",
    }
    if report.status!="GO":
        consolidated["stage"]="NO_GO"
        consolidated["failure_reason"]="preflight failed"
        atomic_json(evidence/"PRIMERA_PRUEBA_CEO_RESULTADO.json",consolidated)
        print(json.dumps(consolidated,ensure_ascii=False))
        return 2

    if args.preflight_only:
        consolidated["stage"]="PREFLIGHT_GO"
        atomic_json(evidence/"PRIMERA_PRUEBA_CEO_RESULTADO.json",consolidated)
        print(json.dumps(consolidated,ensure_ascii=False))
        return 0

    gate=base/"run_b29_b30_full_field_gate.ps1"
    code,output=run_powershell(
        gate,profile_dir=profile,port=report.selected_cdp_port,timeout=args.timeout
    )
    (evidence/"FIRST_TRIAL_FIELD_GATE.log").write_text(bounded_text(output),encoding="utf-8")
    consolidated["evidence"]["field_gate_log"]=str(evidence/"FIRST_TRIAL_FIELD_GATE.log")
    consolidated["field_gate_status"]="PASS" if code==0 else "FAIL"

    field_path=evidence/"BROWSER_FIELD_STATE.json"
    field=read_json(field_path) if field_path.is_file() else {}
    criteria=go_criteria(report,field)
    consolidated.update(criteria)
    consolidated["BROWSER_FIELD_VERIFIED"]=bool(field.get("BROWSER_FIELD_VERIFIED") is True)
    consolidated["stage"]="FIELD_VERIFIED_READY_FOR_B38" if criteria["first_autodevelopment_launch_allowed"] else "FIELD_GATE_FAILED"
    if not criteria["first_autodevelopment_launch_allowed"]:
        consolidated["failure_reason"]=bounded_text(
            "B29-B30 did not produce a valid field state. B38 remains blocked."
        )
    consolidated["b38_automatically_started"]=False
    consolidated["next_action"]=(
        "Run EJECUTAR_B38_CANDIDATE.cmd manually as the separate first autodevelopment test."
        if criteria["first_autodevelopment_launch_allowed"]
        else "Inspect field-gate evidence and correct the failed physical condition."
    )
    atomic_json(evidence/"PRIMERA_PRUEBA_CEO_RESULTADO.json",consolidated)
    print(json.dumps(consolidated,ensure_ascii=False))
    return 0 if criteria["first_autodevelopment_launch_allowed"] else 3


if __name__=="__main__":
    raise SystemExit(main())
