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


def load_build_identity(base: Path) -> dict:
    candidates = [
        (base / ".." / ".." / "CEO_FIRST_TRIAL_LAB.json").resolve(),
        (base / "CEO_FIRST_TRIAL_LAB.json").resolve(),
    ]
    for path in candidates:
        if path.is_file():
            try:
                row=json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(row,dict):
                    return row
            except Exception:
                pass
    return {"build_id":"SOURCE_TREE","source_sha":"","artifact_kind":"source-tree"}



def reset_owned_browser(*, base: Path, profile_dir: Path) -> tuple[bool, str]:
    """Close only Chrome/Edge processes using CEO's exclusive profile."""
    if os.name != "nt":
        return True, "non-Windows: no owned browser reset required"
    script=base/"recover_first_trial.ps1"
    if not script.is_file():
        return False, f"recovery script missing: {script}"
    proc=subprocess.run(
        [
            "powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(script),
            "-ProfileDir",str(profile_dir),
        ],
        capture_output=True,text=True,timeout=45,
        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
    )
    output=((proc.stdout or "")+"\n"+(proc.stderr or "")).strip()
    return proc.returncode==0,bounded_text(output,12000)


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

    reset_ok,reset_detail=reset_owned_browser(base=base,profile_dir=profile)
    if not reset_ok:
        failure={
            "schema_version":1,
            "created_at_epoch":int(time.time()),
            "stage":"OWNED_BROWSER_RESET_FAILED",
            "profile_dir":str(profile),
            "detail":reset_detail,
            "BROWSER_FIELD_VERIFIED":False,
            "first_autodevelopment_launch_allowed":False,
        }
        atomic_json(evidence/"PRIMERA_PRUEBA_CEO_RESULTADO.json",failure)
        print(json.dumps(failure,ensure_ascii=False))
        return 6
    print("[OK] Navegador anterior de CEO cerrado/limpio; login persistente conservado.")

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
        "owned_browser_reset_status":"PASS",
        "owned_browser_reset_detail":reset_detail,
        "preflight_status":report.status,
        "selected_cdp_port":report.selected_cdp_port,
        "restart_gate_status":"NOT_RUN",
        "field_gate_status":"NOT_RUN",
        "BROWSER_FIELD_VERIFIED":False,
        "first_autodevelopment_launch_allowed":False,
        "api_calls_required":0,
        "production_promotion_allowed":False,
        "automatic_merge_allowed":False,
        "automatic_purchase_allowed":False,
        "b38_automatically_started":False,
        "verification_levels":{
            "CI_VERIFIED":True,
            "WINDOWS_PHYSICAL_VERIFIED":False,
            "REAL_CHATGPT_VERIFIED":False,
        },
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

    # Functional campaign: one browser session, one provider, one isolated trial directory.
    build=load_build_identity(base)
    trial_dir=(evidence/"trials"/report.trial_id).resolve()
    trial_dir.mkdir(parents=True,exist_ok=False)
    canonical_state=(evidence/"BROWSER_FIELD_STATE.json").resolve()
    atomic_json(evidence/"CURRENT_TRIAL.json",{
        "trial_id":report.trial_id,
        "build_id":build.get("build_id",""),
        "source_sha":build.get("source_sha",""),
        "evidence_dir":str(trial_dir),
        "status":"RUNNING",
    })
    consolidated["build_id"]=build.get("build_id","")
    consolidated["source_sha"]=build.get("source_sha","")
    consolidated["trial_evidence_dir"]=str(trial_dir)
    consolidated["restart_gate_status"]="SKIPPED_SEPARATE_RESILIENCE_TEST"
    consolidated["restart_gate_required_for_first_functional_trial"]=False

    runner=base/"run_field_campaign.py"
    cmd=[
        sys.executable,
        str(runner),
        "--provider","chatgpt-web",
        "--profile-dir",str(profile),
        "--evidence-dir",str(trial_dir),
        "--canonical-out",str(canonical_state),
        "--trial-id",report.trial_id,
        "--port",str(report.selected_cdp_port),
        "--timeout",str(args.timeout),
    ]
    proc=subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=max(1200,args.timeout*12),
        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
    )
    output=bounded_text(((proc.stdout or "")+"\n"+(proc.stderr or "")).strip())
    (trial_dir/"FIRST_TRIAL_FIELD_GATE.log").write_text(output,encoding="utf-8")
    consolidated["evidence"]["field_gate_log"]=str(trial_dir/"FIRST_TRIAL_FIELD_GATE.log")
    consolidated["field_gate_status"]="PASS" if proc.returncode==0 else "FAIL"

    field_path=evidence/"BROWSER_FIELD_STATE.json"
    field=read_json(field_path) if field_path.is_file() else {}
    evidence_fingerprints={}
    for name in (
        "B09_B14_PHYSICAL_GATE.json",
        "B15_B18_PHYSICAL_GATE.json",
        "B19_B20_CODE_GATE.json",
        "BROWSER_FIELD_STATE.json",
        "FIELD_CAMPAIGN_RESULT.json",
    ):
        p=trial_dir/name
        if p.is_file():
            import hashlib
            evidence_fingerprints[name]={
                "sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
                "size_bytes":p.stat().st_size,
                "mtime_ns":p.stat().st_mtime_ns,
                "trial_id":report.trial_id,
            }
    consolidated["evidence_fingerprints"]=evidence_fingerprints
    criteria=go_criteria(report,field)
    consolidated.update(criteria)
    consolidated["BROWSER_FIELD_VERIFIED"]=bool(field.get("BROWSER_FIELD_VERIFIED") is True)
    physical_ok=bool(field.get("BROWSER_FIELD_VERIFIED") is True)
    consolidated["verification_levels"]={
        "CI_VERIFIED":True,
        "WINDOWS_PHYSICAL_VERIFIED":physical_ok,
        "REAL_CHATGPT_VERIFIED":physical_ok,
    }
    consolidated["stage"]="FIELD_VERIFIED_READY_FOR_B38" if criteria["first_autodevelopment_launch_allowed"] else "FIELD_GATE_FAILED"
    if not criteria["first_autodevelopment_launch_allowed"]:
        consolidated["failure_reason"]=bounded_text(
            "B29-B30 did not produce a valid field state. B38 remains blocked."
        )
    consolidated["b38_automatically_started"]=False
    consolidated["next_action"]=(
        "Run EJECUTAR_B38_CANDIDATE.cmd manually as the separate first autodevelopment test."
        if criteria["first_autodevelopment_launch_allowed"]
        else "Inspect only this trial's FIELD_CAMPAIGN_RESULT.json; previous trials are isolated."
    )
    atomic_json(evidence/"CURRENT_TRIAL.json",{
        "trial_id":report.trial_id,
        "build_id":consolidated.get("build_id",""),
        "source_sha":consolidated.get("source_sha",""),
        "evidence_dir":str(trial_dir),
        "status":consolidated["stage"],
        "field_verified":bool(consolidated["BROWSER_FIELD_VERIFIED"]),
    })
    atomic_json(evidence/"PRIMERA_PRUEBA_CEO_RESULTADO.json",consolidated)
    print(json.dumps(consolidated,ensure_ascii=False))
    return 0 if criteria["first_autodevelopment_launch_allowed"] else 3


if __name__=="__main__":
    raise SystemExit(main())
