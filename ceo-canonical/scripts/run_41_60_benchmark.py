from __future__ import annotations
import json, tempfile, threading, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.integrity_engineering import *
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.contracts import WorkerProvider, WorkerRequest

out={"suite":"ROADMAP_41_60","version":"0.9.0-dev9","windows_physical":False}

# 41 hotspots on real tree with synthetic local history evidence
h=CodeHotspotDetector().analyze(ROOT, git_hotspots=[{"path":"ceo_core/scheduler.py","commit_touches":30},{"path":"ceo_core/store.py","commit_touches":12}], failure_counts={"ceo_core/scheduler.py":2})
out["hotspots"]={"files":h["files"],"top":h["hotspots"][:5],"pass":bool(h["hotspots"])}

# 42-43 debt ledger + ranking at scale
s=ProjectState(goal="benchmark")
ledger=TechnicalDebtLedger()
for i in range(1000):
    ledger.record(s,title=f"debt-{i}",component=f"component-{i%50}",impact=(i%10)/10,risk=((i*3)%10)/10,recurrence=((i*7)%10)/10,effort=.1+(i%9)/10,evidence=[f"E{i}"])
ranked=DebtPrioritizer().prioritize(ledger.open_items(s))
out["technical_debt"]={"items":len(ranked),"sorted":all(ranked[i]["priority_score"]>=ranked[i+1]["priority_score"] for i in range(len(ranked)-1)),"top":ranked[:3]}

# 44 refactor safety
rf=RefactorSafetyHarness(); base=rf.baseline(outputs={"api":"same","scheduler":"same"},contract_hashes={"worker":"v1"},test_ids=[f"t{i}" for i in range(50)])
out["refactor_safety"]={"same":rf.compare(base,outputs={"api":"same","scheduler":"same"},contract_hashes={"worker":"v1"},passed_tests=[f"t{i}" for i in range(50)])["safe"],"drift_rejected":not rf.compare(base,outputs={"api":"changed","scheduler":"same"},contract_hashes={"worker":"v1"},passed_tests=[f"t{i}" for i in range(50)])["safe"]}

# 45 architecture drift on real imports, inject forbidden current edge in copy
ad=ArchitectureDriftDetector(); current=ad.imports(ROOT); baseline={k:set(v) for k,v in current.items()}; fake={k:set(v) for k,v in current.items()}; fake.setdefault("ceo_core.ui",set()).add("ceo_core.sqlite_store")
r=ad.compare(baseline,fake,forbidden_edges=[("ceo_core.ui","ceo_core.sqlite_store")]); out["architecture"]={"modules":len(current),"injected_drift_detected":r["drift"],"violations":len(r["violations"])}

# 46 interface contract
ic=InterfaceContractVerifier(); snap=ic.snapshot_callable(WorkerProvider.execute); out["interface_contract"]={"self_compatible":ic.verify(snap,WorkerProvider.execute)["compatible"],"digest":snap["digest"]}

# 47 state machine exhaustive edge validation
sm=StateMachineVerifier(); legal=sum(len(v) for v in sm.TASK_TRANSITIONS.values()); checked=0
for a,bs in sm.TASK_TRANSITIONS.items():
    for b in bs: assert sm.valid_transition(a,b); checked+=1
out["state_machine"]={"legal_edges":legal,"checked":checked,"invalid_direct_waiting_complete":not sm.valid_transition("waiting","complete")}

# 48 property based test 10k cases
prop=PropertyTestEngine().run(lambda rng,i:(rng.randint(-10**6,10**6),rng.randint(-10**6,10**6)),lambda x:x[0]+x[1]==x[1]+x[0],cases=10000,seed=41)
out["property_testing"]={"cases":prop["cases"],"passed":prop["passed"],"failures":len(prop["failures"])}

# 49 fuzzing against workspace containment semantics
from ceo_core.execution_integrity import WorkspaceGuard
with tempfile.TemporaryDirectory() as td:
    guard=WorkspaceGuard(td)
    fuzz=InputFuzzer().fuzz(lambda x: guard.resolve(str(x)))
out["input_fuzz"]={"cases":fuzz["cases"],"passed":fuzz["passed"],"unhandled":len(fuzz["unhandled_crashes"])}

# 50 concurrency fuzz 5k exactly accounted operations
lock=threading.Lock(); counter={"n":0}
def op(_):
    with lock: counter["n"]+=1
conc=ConcurrencyFuzzer().run(op,lambda:counter["n"]==5000,workers=32,operations=5000,seed=50)
out["concurrency"]={"operations":5000,"workers":32,"passed":conc["passed"],"counter":counter["n"]}

# 51 crash injection at every phase
phases=["prepared","reserved","executing","persisting","committed"]
def operation(cp):
    for p in phases: cp(p)
    return "done"
ci=CrashInjector(); crashes=[ci.run(operation,crash_at=p) for p in phases]
out["crash_injection"]={"phases":len(phases),"all_injected":all(x["crashed"] for x in crashes),"clean_run":not ci.run(operation,crash_at=None)["crashed"]}

# 52 recovery oracle
before=ProjectState(goal="x"); task=Task(title="x",status=TaskStatus.RUNNING); before.tasks[task.id]=task
recovered=before.model_copy(deep=True); recovered.tasks[task.id].status=TaskStatus.RETRY
oracle=CrashRecoveryOracle().verify(before,recovered)
out["recovery_oracle"]={"consistent":oracle["consistent"],"task_count_preserved":oracle["task_count_preserved"]}

# 53 transactions: 500 rollbacks + 500 commits
tr=TransactionalProjectState(); ts=ProjectState(goal="start"); rolled=committed=0
for i in range(500):
    try:
        with tr.transaction(ts,name=f"rollback-{i}"):
            ts.goal="bad"; raise RuntimeError("inject")
    except RuntimeError:
        rolled += int(ts.goal!="bad")
for i in range(500):
    with tr.transaction(ts,name=f"commit-{i}") as tx:
        ts.goal=f"good-{i}"; tx.commit(); committed+=1
out["transactions"]={"rollbacks_preserved":rolled,"commits":committed,"final":ts.goal}

# 54 exactly once, 5000 duplicate attempts after one commit
eos=ExactlyOnceExternalActionModel(); es=ProjectState(goal="x"); first=eos.begin(es,key="payment:1",operation="spend",preview_digest="p"); eos.commit(es,"payment:1",{"receipt":"r"}); duplicates=0
for i in range(5000): duplicates += int(not eos.begin(es,key="payment:1",operation="spend",preview_digest="p")["execute"])
out["exactly_once"]={"duplicates_blocked":duplicates,"committed_count":es.metadata[eos.KEY]["payment:1"]["committed_count"]}

# 55-60 safety matrix
core=IntegrityEngineeringCore(); ss=ProjectState(goal="x"); scenarios=[
    SideEffectDefinition("read",["read"]),
    SideEffectDefinition("write",["write"],external=True),
    SideEffectDefinition("mail",["communicate","network"],external=True,communicates=True),
    SideEffectDefinition("buy",["spend","network"],external=True,spends_money=True),
    SideEffectDefinition("sensitive",["write"],external=True,sensitive_data=True),
    SideEffectDefinition("delete",["delete"],reversible=False,external=True,destructive=True),
]
rows=[]
for d in scenarios:
    core.side_effects.register(ss,d); pre=core.preflight(ss,tool=d.tool,tool_row={"external_effects":d.external,"destructive":d.destructive},kwargs={"target":"resource","secret_token":"x"},cost_estimate=100 if d.spends_money else 0,evidence_quality=.8,approved=False)
    rows.append({"tool":d.tool,"risk":pre["risk"]["risk"],"approval":pre["approval"]["decision"],"secret_redacted":pre["preview"]["arguments"]["secret_token"]=="<redacted>"})
out["action_safety"]={"scenarios":rows,"risk_monotonic_delete_gt_read":rows[-1]["risk"]>rows[0]["risk"],"irreversible_requires_approval":rows[-1]["approval"]=="REQUIRE_APPROVAL","all_secrets_redacted":all(r["secret_redacted"] for r in rows)}

out["pass"]=all([
    out["hotspots"]["pass"], out["technical_debt"]["sorted"], out["refactor_safety"]["same"], out["refactor_safety"]["drift_rejected"],
    out["architecture"]["injected_drift_detected"],out["interface_contract"]["self_compatible"],out["state_machine"]["invalid_direct_waiting_complete"],out["property_testing"]["passed"],out["input_fuzz"]["passed"],out["concurrency"]["passed"],out["crash_injection"]["all_injected"],out["recovery_oracle"]["consistent"],out["transactions"]["rollbacks_preserved"]==500,out["exactly_once"]["committed_count"]==1,out["action_safety"]["irreversible_requires_approval"]
])
report=ROOT/"reports"/"INTEGRITY_41_60_BENCHMARK.json"; report.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8"); print(json.dumps({"pass":out["pass"],"report":str(report),"property_cases":10000,"concurrency_ops":5000,"duplicates_blocked":duplicates},indent=2))
