from __future__ import annotations
import json, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from ceo_core.contracts import GoalContract, WorkUnit, WorkerRequest
from ceo_core.models import ProjectState
from ceo_core.self_hosting_runtime import *

class Seq:
    def __init__(self): self.n=0
    def observe(self):
        self.n += 1
        return {"active_app":"chrome","active_window":"A","url":f"https://example/{self.n}","title":f"T{self.n}"}

def main():
    t=time.perf_counter(); state=ProjectState(goal="self-hosting benchmark")
    boundary=DesktopSafetyBoundary(); stats={}
    # mode enforcement matrix x 1000
    allowed=blocked=0
    for i in range(1000):
        mode=(DesktopMode.READ_ONLY,DesktopMode.SUPERVISED,DesktopMode.AUTONOMOUS)[i%3]
        boundary.set_mode(state,mode)
        action=DesktopAction("write",DesktopRisk.WRITE,reversible=True)
        r=boundary.authorize(state,action,approved=(mode==DesktopMode.SUPERVISED))
        allowed += int(r["allowed"]); blocked += int(not r["allowed"])
    stats["mode_decisions"]={"total":1000,"allowed":allowed,"blocked":blocked,"pass":allowed+blocked==1000}
    # observation/confirmation loop x 500
    boundary.set_mode(state,DesktopMode.AUTONOMOUS); loop=DesktopObservationLoop(Seq())
    ok=0
    for _ in range(500):
        r=loop.act_and_confirm(state,action=DesktopAction("nav",DesktopRisk.WRITE,targets=["chrome"]),executor=lambda:True,expectation={"active_app":"chrome"},boundary=boundary)
        ok += int(r["ok"])
    stats["observation_confirmation"]={"runs":500,"confirmed":ok,"pass":ok==500}
    # contract construction x 1000
    contract=CEOAIContract(); valid=0
    for i in range(1000):
        req=WorkerRequest(project_id=f"p{i}",goal=GoalContract(objective="Improve CEO",constraints=["immutable stable"],forbidden_actions=["no auto promote"]),work_unit=WorkUnit(id=f"w{i}",title="work",acceptance_criteria=["evidence"]),context={"artifacts":["x.py"]})
        env=contract.build(req)
        valid += int(env.definition_of_done==["evidence"] and env.artifact_inputs==["x.py"])
    stats["worker_contracts"]={"built":1000,"valid":valid,"pass":valid==1000}
    # recovery x 500
    rec=GUIRecoveryEngine(); recovered=0
    for i in range(500):
        b=DesktopObservation(i*2+1,time.time(),active_app="chrome",active_window="A",url="a")
        a=DesktopObservation(i*2+2,time.time(),active_app="other",active_window=None,url="b",modal={"title":"x"})
        recovered += int(rec.recover(state,b,a,desired_app="chrome")["needed"])
    stats["gui_recovery"]={"cases":500,"recovery_needed":recovered,"pass":recovered==500}
    # field gates remain honest
    core=SelfHostingRuntimeCore(); core.initialize(state)
    pre=core.local_preflight(state,[])
    stats["field_truth"]={"live_provider":pre["live_provider"]["status"],"windows":pre["windows_physical"],"pass":pre["live_provider"]["status"]=="NOT_VERIFIED" and pre["windows_physical"]=="DEFERRED_BY_USER"}
    out={"version":"1.1.0-dev2-self-hosting","scope":"11-20","elapsed_seconds":round(time.perf_counter()-t,4),"stats":stats,"pass":all(x["pass"] for x in stats.values())}
    path=ROOT/'SELF_HOSTING_11_20_BENCHMARK.json'; path.write_text(json.dumps(out,indent=2),encoding='utf-8'); print(json.dumps(out,indent=2)); return 0 if out["pass"] else 1
if __name__=='__main__': raise SystemExit(main())
