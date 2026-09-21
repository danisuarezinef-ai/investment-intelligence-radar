from __future__ import annotations

import json
import pathlib
import re
import sys
from dataclasses import asdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANON = ROOT / "ceo-canonical"
sys.path.insert(0, str(CANON))

from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.task_roles_v2 import TaskRole
from ceo_core.productive_truth_v2 import ProductiveTruthV2
from ceo_core.useful_output_watchdog_v2 import UsefulOutputWatchdogV2
from ceo_core.decomposer import TaskDecomposer
from ceo_core.goal_completion_gate import GoalCompletionGate
from ceo_core.release_firewall import ReleaseQualificationFirewall

RESULTS = []

def record(idx:int, family:str, name:str, ok:bool, detail=""):
    RESULTS.append({
        "pass": idx,
        "family": family,
        "name": name,
        "ok": bool(ok),
        "detail": str(detail)[:1200],
    })

def add(state:ProjectState, task:Task):
    state.tasks[task.id]=task
    state.root_task_ids.append(task.id)
    return task

# 1-50 Scheduler/recovery invariants.
for i in range(50):
    idx=i+1
    recoveries=i%10
    mode=i%5
    state=ProjectState(goal=f"scheduler-matrix-{i}")
    # Historical recoveries are intentionally rebased by ProductiveTruthV2. Establish
    # the epoch first, then add only recoveries that occur in the current epoch.
    state.metadata["worker_recoveries"]=0
    if mode==0:
        add(state,Task(title="productive ready",status=TaskStatus.READY,metadata={"task_role":"productive"}))
    elif mode==1:
        add(state,Task(title="productive retry",status=TaskStatus.RETRY,metadata={"task_role":"productive"}))
    elif mode==2:
        add(state,Task(title="productive running",status=TaskStatus.RUNNING,metadata={"task_role":"productive"}))
    elif mode==3:
        add(state,Task(title="provider wait",status=TaskStatus.WAITING,metadata={"task_role":"productive","waiting_provider_v1":{"active":True}}))
        state.metadata["provider_wait_v1"]={"active":True,"category":"transient"}
    else:
        add(state,Task(title="internal recovery",status=TaskStatus.READY,metadata={"task_role":"control","autonomy_recovery":True}))
    try:
        truth_engine=ProductiveTruthV2(recovery_trip=4)
        truth_engine.assess(state)
        state.metadata["worker_recoveries"]=recoveries
        truth=truth_engine.assess(state)
        wd=UsefulOutputWatchdogV2().tick(state)
        if mode in {0,1,2}:
            ok=(not truth.stalled and wd.status not in {"BLOQUEADO","ATASCADO"})
        elif mode==3:
            ok=(truth.status=="waiting_provider" and not truth.stalled and wd.fallback_action=="provider_wait")
        else:
            ok=(recoveries<4 or wd.status in {"ATASCADO","BLOQUEADO","REPLANIFICANDO"})
        record(idx,"scheduler",f"recovery={recoveries},mode={mode}",ok,{"truth":truth.to_dict(),"wd":wd.to_dict()})
    except Exception as exc:
        record(idx,"scheduler",f"recovery={recoveries},mode={mode}",False,repr(exc))

# 51-100 Decomposition invariants: one explicit simple file is one bounded compact job.
for i in range(50):
    idx=51+i
    pad=" detalle"* (i*7)
    goal=f"Crea un archivo RESULT_{i}.md con un resumen breve.{pad}"
    try:
        profile=TaskDecomposer._complexity_profile(goal)
        state=TaskDecomposer().plan(goal)
        ok=(profile["mode"]=="compact" and len(state.leaf_tasks)<=3)
        record(idx,"decomposition",f"simple-file-len={len(goal)}",ok,profile)
    except Exception as exc:
        record(idx,"decomposition",f"simple-file-{i}",False,repr(exc))

# 101-150 Completion invariants: a verified concrete single-file deliverable must not need LLM audit generations.
for i in range(50):
    idx=101+i
    state=ProjectState(goal=f"Create OUTPUT_{i}.md",goal_deliverables=[f"OUTPUT_{i}.md"])
    state.metadata["real_work_intake_v1"]={"kind":"single_deliverable"}
    state.metadata["goal_continuity_generation"]=0
    prod=add(state,Task(
        title="Create deliverable",
        status=TaskStatus.COMPLETE,
        result="created",
        metadata={
            "task_role":"productive",
            "artifacts":[f"OUTPUT_{i}.md"],
            "verified_artifacts":[f"OUTPUT_{i}.md"],
            "acceptance_evidence":True,
        },
    ))
    ver=add(state,Task(
        title="Independent verification",
        status=TaskStatus.COMPLETE,
        result="verified",
        metadata={
            "task_role":"verification",
            "independently_verified":True,
            "verification_application":True,
            "artifacts":[f"OUTPUT_{i}.md"],
        },
    ))
    state.metadata["deliverable_evidence"]={
        f"OUTPUT_{i}.md":{"task_id":prod.id,"sha256":"a"*64,"size_bytes":10,"ref":f"OUTPUT_{i}.md"}
    }
    try:
        gate=GoalCompletionGate()
        refs=[prod.id,ver.id]
        verdict=gate.evaluate(state,evidence_refs=refs)
        ok=verdict.eligible
        record(idx,"completion",f"single-file-verified-{i}",ok,verdict.to_dict())
    except Exception as exc:
        record(idx,"completion",f"single-file-verified-{i}",False,repr(exc))

# 151-200 Provider capability invariants: provider waiting is not core shutdown.
workmode=(CANON/"scripts/ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
for i in range(50):
    idx=151+i
    # Alternate source-level invariants and state-level provider-wait behavior.
    if i%5==0:
        ok="provider_wait_v1" in workmode
        detail="provider wait state exists"
    elif i%5==1:
        # Starting/keeping scheduler must not be syntactically nested under execution_enabled.
        suspicious=bool(re.search(r"if\s+(?:not\s+)?self\.execution_enabled\s*:\s*(?:\n[^\n]*){0,6}\n\s*self\.scheduler\s*=",workmode))
        ok=not suspicious
        detail=f"suspicious_scheduler_gate={suspicious}"
    elif i%5==2:
        # New-project API must exist independently of live provider truth.
        ok="/api/project/start" in workmode or "/api/project" in workmode
        detail="project intake route present"
    elif i%5==3:
        # A provider outage must be represented as waiting, not invalid credential.
        ok=("gemini-authenticated-waiting" in workmode and "gemini_key_recognized" in workmode)
        detail="authenticated waiting semantics present"
    else:
        # Provider wait must not consume worker-recovery budget in productive truth/watchdog.
        state=ProjectState(goal="provider wait")
        state.metadata["worker_recoveries"]=9
        state.metadata["provider_wait_v1"]={"active":True,"category":"network"}
        add(state,Task(title="needs provider",status=TaskStatus.WAITING,metadata={"task_role":"productive","waiting_provider_v1":{"active":True}}))
        truth=ProductiveTruthV2().assess(state)
        ok=(truth.status=="waiting_provider" and not truth.stalled)
        detail=truth.to_dict()
    record(idx,"provider",f"provider-capability-{i}",ok,detail)

# 201-250 Release governance invariants.
manifest_dir=ROOT/"ceo-updates"
quarantine=json.loads((ROOT/"audit"/"LEGACY_RELEASE_QUARANTINE.json").read_text(encoding="utf-8"))
quarantined_manifests=set(quarantine.get("invalid_stable_manifests") or [])
quarantined_numeric={
    str(k):set(v) for k,v in (quarantine.get("numeric_version_collisions") or {}).items()
}
manifests=[]
for p in sorted(manifest_dir.glob("DEV*_MANIFEST_UNSIGNED.json")):
    try:
        m=json.loads(p.read_text(encoding="utf-8"))
        manifests.append((p,m))
    except Exception:
        pass
quals={}
for p in sorted(manifest_dir.glob("DEV*_QUALIFICATION.json")):
    try:
        quals[p.stem.replace("_QUALIFICATION","")]=json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass

zip_numeric={}
for p in sorted(manifest_dir.glob("CEO_*.zip")):
    m=re.search(r"CEO_(\d+\.\d+\.\d+)-",p.name)
    if m:
        zip_numeric.setdefault(m.group(1),set()).add(p.name)

for i in range(50):
    idx=201+i
    if i < len(manifests):
        p,m=manifests[i]
        key=p.stem.replace("_MANIFEST_UNSIGNED","")
        q=quals.get(key,{})
        stable=(m.get("channel")=="stable" or m.get("release_status")=="release")
        report=ReleaseQualificationFirewall.evaluate(
            q,channel=str(m.get("channel") or ""),release_status=str(m.get("release_status") or "")
        )
        if stable and not report.allowed:
            ok=p.name in quarantined_manifests
        else:
            ok=report.allowed if stable else True
        detail={
            "manifest":p.name,
            "stable":stable,
            "firewall_allowed":report.allowed,
            "problems":list(report.problems),
            "quarantined":p.name in quarantined_manifests,
        }
        record(idx,"release",p.name,ok,detail)
    else:
        if i%2==0:
            bad={}
            for base,names in zip_numeric.items():
                if len(names)>1:
                    expected=quarantined_numeric.get(base,set())
                    if not names.issubset(expected):
                        bad[base]={"artifacts":sorted(names),"quarantined":sorted(expected)}
            record(idx,"release","numeric-version-collisions-contained",not bad,bad)
        else:
            # A synthetic local-only candidate must never pass the stable firewall.
            synthetic={
                "tests_passed":True,
                "security_passed":True,
                "clean_extract_passed":True,
                "package_contract_passed":True,
                "production_ready":False,
                "field_validation_pending":True,
            }
            report=ReleaseQualificationFirewall.evaluate(
                synthetic,channel="stable",release_status="release"
            )
            record(idx,"release","firewall-rejects-local-only-candidate",not report.allowed,report.to_dict())

# 251-300 Launcher/updater/package critical-path invariants.
launcher=(CANON/"scripts/launch_current.py").read_text(encoding="utf-8")
updater=(CANON/"ceo_core/in_app_updater.py").read_text(encoding="utf-8")
package=json.loads((CANON/"CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
required=set(package.get("required_paths") or [])
critical=[
    "scripts/ceo_stdlib_work_mode.py",
    "scripts/launch_current.py",
    "ceo_core/in_app_updater.py",
    "CEO_UPDATE_PACKAGE.json",
]
for i in range(50):
    idx=251+i
    kind=i%10
    if kind==0:
        ok=all((CANON/p).is_file() for p in critical); detail="critical paths exist"
    elif kind==1:
        ok=all(p in required for p in critical if p!="CEO_UPDATE_PACKAGE.json"); detail="critical paths in contract"
    elif kind==2:
        ok="recover_interrupted_update" in launcher; detail="launcher invokes recovery"
    elif kind==3:
        ok=("previous" in updater.lower() and "rollback" in updater.lower()); detail="rollback state exists"
    elif kind==4:
        ok=("confirm" in updater.lower()); detail="human confirmation concept exists"
    elif kind==5:
        # Critical startup errors must not all disappear silently.
        silent=len(re.findall(r"except\s+Exception[^:]*:\s*(?:#.*\n\s*)?pass\b",launcher))
        ok=(silent==0); detail={"silent_launcher_exceptions":silent}
    elif kind==6:
        silent=len(re.findall(r"except\s+Exception[^:]*:\s*(?:#.*\n\s*)?pass\b",updater))
        ok=(silent==0); detail={"silent_updater_exceptions":silent}
    elif kind==7:
        ok="atomic" in updater.lower() or ".replace(" in updater; detail="atomic pointer/write primitive present"
    elif kind==8:
        ok="health" in launcher.lower(); detail="launcher has health concept"
    else:
        # Bundled fallback must exist if update pointer is dead.
        ok=("bundled-fallback" in launcher and "_safe_pointer" in launcher); detail="dead pointer fallback present"
    record(idx,"launcher_updater",f"critical-{i}",ok,detail)

assert len(RESULTS)==300, len(RESULTS)
passed=sum(1 for r in RESULTS if r["ok"])
failed=300-passed
by_family={}
for r in RESULTS:
    f=by_family.setdefault(r["family"],{"pass":0,"fail":0})
    f["pass" if r["ok"] else "fail"]+=1
report={
    "schema":1,
    "total":300,
    "passed":passed,
    "failed":failed,
    "families":by_family,
    "failures":[r for r in RESULTS if not r["ok"]],
    "all_results":RESULTS,
}
out=ROOT/"audit"/"CEO_300_PASS_AUDIT.json"
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k not in {"all_results","failures"}},indent=2))
print("FAILURES",failed)
