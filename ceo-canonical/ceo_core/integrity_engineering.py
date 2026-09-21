from __future__ import annotations

import ast
import copy
import inspect
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable

from .models import ProjectState, TaskStatus


def _clip(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


# 41. Hotspots -----------------------------------------------------------------
class CodeHotspotDetector:
    """Ranks files by churn + complexity + failures; all inputs are local evidence."""

    def analyze(self, root: str | Path, *, git_hotspots: Iterable[dict[str, Any]] = (), failure_counts: dict[str, int] | None = None) -> dict[str, Any]:
        base = Path(root).resolve(); failure_counts = failure_counts or {}
        touches = {str(r.get("path")): int(r.get("commit_touches", 0)) for r in git_hotspots}
        rows = []
        for path in sorted(base.rglob("*.py")):
            if any(x in path.parts for x in {".git", ".venv", "venv", "__pycache__"}):
                continue
            rel = path.relative_to(base).as_posix()
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(text)
            except Exception:
                continue
            branches = sum(isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.Match, ast.BoolOp, ast.comprehension)) for n in ast.walk(tree))
            funcs = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree))
            lines = max(1, len(text.splitlines()))
            churn = touches.get(rel, 0); failures = int(failure_counts.get(rel, 0))
            complexity = branches + funcs * .5
            score = min(1.0, .35 * min(1, churn / 12) + .3 * min(1, complexity / 40) + .2 * min(1, lines / 800) + .15 * min(1, failures / 5))
            rows.append({"path": rel, "score": round(score, 5), "commit_touches": churn, "complexity": round(complexity, 2), "lines": lines, "failures": failures})
        rows.sort(key=lambda r: (-r["score"], r["path"]))
        return {"files": len(rows), "hotspots": rows[:100], "network_checked": False}


# 42-43. Technical debt ---------------------------------------------------------
@dataclass(slots=True)
class DebtItem:
    id: str
    title: str
    component: str
    impact: float
    risk: float
    recurrence: float
    effort: float
    source: str = "observed"
    status: str = "open"
    evidence: list[str] = field(default_factory=list)


class TechnicalDebtLedger:
    KEY = "technical_debt_ledger_v1"
    def record(self, state: ProjectState, *, title: str, component: str, impact: float=.5, risk: float=.5, recurrence: float=.5, effort: float=.5, source: str="observed", evidence: Iterable[str]=()) -> DebtItem:
        did = sha256(f"{component}|{title}".encode()).hexdigest()[:20]
        item = DebtItem(did, title, component, _clip(impact), _clip(risk), _clip(recurrence), max(.01, float(effort)), source, "open", list(evidence))
        rows = state.metadata.setdefault(self.KEY, {})
        if did in rows:
            old = rows[did]; old["evidence"] = sorted(set(old.get("evidence", [])) | set(item.evidence)); old["impact"] = max(old["impact"], item.impact); old["risk"] = max(old["risk"], item.risk); old["recurrence"] = max(old["recurrence"], item.recurrence)
            return DebtItem(**old)
        rows[did] = asdict(item); return item
    def resolve(self, state: ProjectState, debt_id: str, evidence: str) -> bool:
        row = state.metadata.setdefault(self.KEY, {}).get(debt_id)
        if not row: return False
        row["status"] = "resolved"; row.setdefault("evidence", []).append(evidence); return True
    def open_items(self, state: ProjectState) -> list[DebtItem]:
        return [DebtItem(**r) for r in state.metadata.get(self.KEY, {}).values() if r.get("status") == "open"]


class DebtPrioritizer:
    def prioritize(self, items: Iterable[DebtItem]) -> list[dict[str, Any]]:
        out=[]
        for item in items:
            score=(.38*item.impact + .34*item.risk + .28*item.recurrence)/(max(.1,item.effort)**.55)
            out.append({**asdict(item), "priority_score": round(score, 6)})
        return sorted(out, key=lambda r:(-r["priority_score"],r["id"]))


# 44. Refactor safety -----------------------------------------------------------
class RefactorSafetyHarness:
    def baseline(self, *, outputs: dict[str, Any], contract_hashes: dict[str, str], test_ids: Iterable[str]) -> dict[str, Any]:
        payload={"outputs": outputs, "contract_hashes": contract_hashes, "test_ids": sorted(set(test_ids))}
        return {**payload, "digest": _digest(payload)}
    def compare(self, baseline: dict[str, Any], *, outputs: dict[str, Any], contract_hashes: dict[str, str], passed_tests: Iterable[str]) -> dict[str, Any]:
        changed_outputs=sorted(k for k in set(baseline["outputs"])|set(outputs) if baseline["outputs"].get(k)!=outputs.get(k))
        changed_contracts=sorted(k for k in set(baseline["contract_hashes"])|set(contract_hashes) if baseline["contract_hashes"].get(k)!=contract_hashes.get(k))
        missing_tests=sorted(set(baseline["test_ids"])-set(passed_tests))
        return {"safe": not changed_outputs and not changed_contracts and not missing_tests, "changed_outputs":changed_outputs,"changed_contracts":changed_contracts,"missing_tests":missing_tests}


# 45. Architecture drift --------------------------------------------------------
class ArchitectureDriftDetector:
    def imports(self, root: str | Path, package: str="ceo_core") -> dict[str, set[str]]:
        base=Path(root).resolve(); out={}
        for path in base.rglob("*.py"):
            if any(x in path.parts for x in {".git","__pycache__"}): continue
            rel=path.relative_to(base).with_suffix("").as_posix().replace("/", ".")
            try: tree=ast.parse(path.read_text(encoding="utf-8",errors="ignore"))
            except Exception: continue
            deps=set()
            for n in ast.walk(tree):
                if isinstance(n,ast.Import):
                    deps.update(a.name for a in n.names if a.name.startswith(package))
                elif isinstance(n,ast.ImportFrom) and n.module:
                    if n.level==0 and n.module.startswith(package): deps.add(n.module)
            out[rel]=deps
        return out
    def compare(self, baseline: dict[str, Iterable[str]], current: dict[str, Iterable[str]], *, forbidden_edges: Iterable[tuple[str,str]]=()) -> dict[str, Any]:
        base={k:set(v) for k,v in baseline.items()}; cur={k:set(v) for k,v in current.items()}; added=[]
        for mod,deps in cur.items():
            for dep in deps-base.get(mod,set()): added.append((mod,dep))
        violations=[]
        for src_prefix,dst_prefix in forbidden_edges:
            violations.extend({"source":s,"dependency":d} for s,deps in cur.items() if s.startswith(src_prefix) for d in deps if d.startswith(dst_prefix))
        return {"drift": bool(added or violations), "new_edges":[{"source":a,"dependency":b} for a,b in sorted(added)], "violations":violations}


# 46. Interface contracts -------------------------------------------------------
class InterfaceContractVerifier:
    def snapshot_callable(self, fn: Callable[..., Any]) -> dict[str, Any]:
        sig=inspect.signature(fn)
        row={"parameters":[{"name":n,"kind":str(p.kind),"default":None if p.default is inspect._empty else repr(p.default)} for n,p in sig.parameters.items()],"return":repr(sig.return_annotation)}
        row["digest"]=_digest(row); return row
    def verify(self, expected: dict[str, Any], fn: Callable[..., Any]) -> dict[str, Any]:
        actual=self.snapshot_callable(fn); return {"compatible": actual["digest"]==expected.get("digest"), "expected":expected,"actual":actual}


# 47. State machine verification ------------------------------------------------
class StateMachineVerifier:
    TASK_TRANSITIONS={
        "waiting":{"ready","blocked","cancelled"}, "ready":{"running","blocked","cancelled"}, "running":{"complete","retry","failed","needs_review","partial_complete","complete_with_uncertainty"},
        "retry":{"ready","running","failed","cancelled"}, "blocked":{"ready","failed","cancelled"}, "needs_review":{"complete","retry","failed","superseded"},
        "partial_complete":{"needs_review","complete","retry"}, "complete_with_uncertainty":{"needs_review","complete"}, "failed":{"retry","superseded"}, "complete":{"superseded"}, "superseded":set(), "cancelled":set()
    }
    def valid_transition(self, old: str, new: str) -> bool: return new in self.TASK_TRANSITIONS.get(old,set()) or old==new
    def verify_sequence(self, states: Iterable[str]) -> dict[str, Any]:
        seq=list(states); bad=[]
        for a,b in zip(seq,seq[1:]):
            if not self.valid_transition(a,b): bad.append({"from":a,"to":b})
        return {"valid":not bad,"violations":bad,"states":seq}
    def audit_project(self,state:ProjectState)->dict[str,Any]:
        bad=[]
        for t in state.tasks.values():
            if t.status==TaskStatus.COMPLETE and not t.result: bad.append(f"complete_without_result:{t.id}")
            if t.status==TaskStatus.RUNNING and t.completed_at is not None: bad.append(f"running_with_completed_at:{t.id}")
        return {"valid":not bad,"violations":bad}


# 48. Property based testing -----------------------------------------------------
class PropertyTestEngine:
    def run(self, generator: Callable[[random.Random,int],Any], predicate: Callable[[Any],bool], *, cases:int=100, seed:int=1)->dict[str,Any]:
        rng=random.Random(seed); failures=[]
        for i in range(cases):
            case=generator(rng,i)
            try: ok=bool(predicate(case))
            except Exception as exc: ok=False; failures.append({"index":i,"case":repr(case)[:500],"error":type(exc).__name__}); continue
            if not ok: failures.append({"index":i,"case":repr(case)[:500],"error":"predicate_false"})
        return {"passed":not failures,"cases":cases,"failures":failures[:25],"seed":seed}


# 49. Input fuzzing --------------------------------------------------------------
class InputFuzzer:
    CORPUS=["", " ", "../escape", "..\\escape", "\x00", "' OR 1=1 --", "${SECRET}", "<script>alert(1)</script>", "a"*10000, "{broken", "[]", "null", "🔥"*1000]
    def fuzz(self, target:Callable[[Any],Any], *, extra:Iterable[Any]=())->dict[str,Any]:
        crashes=[]; handled=0
        for i,value in enumerate([*self.CORPUS,*list(extra)]):
            try: target(value); handled+=1
            except (ValueError,TypeError,PermissionError,KeyError): handled+=1
            except Exception as exc: crashes.append({"index":i,"input":repr(value)[:200],"error":type(exc).__name__})
        return {"passed":not crashes,"cases":handled+len(crashes),"handled":handled,"unhandled_crashes":crashes}


# 50. Concurrency fuzzing --------------------------------------------------------
class ConcurrencyFuzzer:
    def run(self, operation:Callable[[int],Any], invariant:Callable[[],bool], *, workers:int=8, operations:int=200, seed:int=1)->dict[str,Any]:
        rng=random.Random(seed); delays=[rng.random()*.003 for _ in range(operations)]; errors=[]
        def wrapped(i:int):
            time.sleep(delays[i]); return operation(i)
        with ThreadPoolExecutor(max_workers=max(1,workers)) as ex:
            futs=[ex.submit(wrapped,i) for i in range(operations)]
            for fut in as_completed(futs):
                try: fut.result()
                except Exception as exc: errors.append(type(exc).__name__)
        inv=False
        try: inv=bool(invariant())
        except Exception: inv=False
        return {"passed":not errors and inv,"operations":operations,"workers":workers,"errors":errors[:25],"invariant":inv,"seed":seed}


# 51-52. Crash injection + oracle -----------------------------------------------
class SimulatedCrash(RuntimeError): pass
class CrashInjector:
    def run(self, operation:Callable[[Callable[[str],None]],Any], *, crash_at:str|None)->dict[str,Any]:
        seen=[]
        def checkpoint(name:str):
            seen.append(name)
            if crash_at is not None and name==crash_at: raise SimulatedCrash(name)
        try: result=operation(checkpoint); return {"crashed":False,"checkpoints":seen,"result":result}
        except SimulatedCrash as exc: return {"crashed":True,"crash_at":str(exc),"checkpoints":seen}

class CrashRecoveryOracle:
    def verify(self, before:ProjectState, recovered:ProjectState, *, idempotency_rows:dict[str,Any]|None=None)->dict[str,Any]:
        violations=[]
        if before.id!=recovered.id: violations.append("project_id_changed")
        if any(t.status==TaskStatus.RUNNING for t in recovered.tasks.values()): violations.append("running_task_after_recovery")
        if any(t.status==TaskStatus.COMPLETE and not t.result for t in recovered.tasks.values()): violations.append("complete_without_result")
        if idempotency_rows:
            dup=[k for k,v in idempotency_rows.items() if int(v.get("committed_count",1))>1]
            if dup: violations.append("duplicate_external_commit:"+",".join(sorted(dup)))
        return {"consistent":not violations,"violations":violations,"task_count_preserved":len(before.tasks)==len(recovered.tasks)}


# 53. Transactional project state ------------------------------------------------
class TransactionalProjectState:
    KEY="project_transactions_v1"
    @contextmanager
    def transaction(self,state:ProjectState,*,name:str="transaction"):
        snapshot=state.model_dump(mode="python"); committed={"value":False}
        txid=sha256(f"{state.id}|{name}|{time.time_ns()}".encode()).hexdigest()[:20]
        state.metadata.setdefault(self.KEY,[]).append({"id":txid,"name":name,"status":"open"})
        class Tx:
            def commit(self): committed["value"]=True
        try:
            yield Tx()
            if not committed["value"]: raise RuntimeError("transaction_not_committed")
            state.metadata[self.KEY][-1]["status"]="committed"
        except Exception:
            restored=ProjectState.model_validate(snapshot)
            state.__dict__.clear(); state.__dict__.update(restored.__dict__)
            state.metadata.setdefault(self.KEY,[]).append({"id":txid,"name":name,"status":"rolled_back"})
            raise


# 54-60 External action safety ---------------------------------------------------
@dataclass(slots=True)
class SideEffectDefinition:
    tool:str
    effects:list[str]
    reversible:bool=True
    external:bool=False
    destructive:bool=False
    spends_money:bool=False
    communicates:bool=False
    sensitive_data:bool=False
    default_targets:list[str]=field(default_factory=list)

class SideEffectRegistry:
    KEY="side_effect_registry_v1"
    EFFECTS={"read","write","delete","spend","communicate","network","execute"}
    def register(self,state:ProjectState,definition:SideEffectDefinition)->None:
        unknown=set(definition.effects)-self.EFFECTS
        if unknown: raise ValueError(f"unknown side effects: {sorted(unknown)}")
        state.metadata.setdefault(self.KEY,{})[definition.tool]=asdict(definition)
    def get(self,state:ProjectState,tool:str,*,fallback:dict[str,Any]|None=None)->SideEffectDefinition:
        row=state.metadata.setdefault(self.KEY,{}).get(tool)
        if row: return SideEffectDefinition(**row)
        f=fallback or {}; external=bool(f.get("external_effects")); destructive=bool(f.get("destructive"))
        effects=["delete" if destructive else "write"] if external else ["read"]
        return SideEffectDefinition(tool,effects,reversible=not destructive,external=external,destructive=destructive)

class ActionPreviewEngine:
    SECRET=re.compile(r"(key|token|secret|password|credential|auth)",re.I)
    def preview(self,definition:SideEffectDefinition,kwargs:dict[str,Any]|None=None)->dict[str,Any]:
        safe={}
        for k,v in (kwargs or {}).items(): safe[str(k)]="<redacted>" if self.SECRET.search(str(k)) else v
        targets=list(definition.default_targets)
        for k in ("path","file","target","url","recipient","repo","project"):
            if k in safe and safe[k] not in (None,"<redacted>"): targets.append(str(safe[k]))
        return {"tool":definition.tool,"effects":definition.effects,"reversible":definition.reversible,"external":definition.external,"destructive":definition.destructive,"spends_money":definition.spends_money,"communicates":definition.communicates,"sensitive_data":definition.sensitive_data,"targets":sorted(set(targets)),"arguments":safe,"executed":False}

class BlastRadiusEstimator:
    def estimate(self,preview:dict[str,Any])->dict[str,Any]:
        effects=set(preview.get("effects",[])); targets=len(preview.get("targets",[])); score=.05
        score += .25 if "delete" in effects else 0
        score += .12 if "write" in effects else 0
        score += .15 if "communicate" in effects or preview.get("communicates") else 0
        score += .12 if "spend" in effects or preview.get("spends_money") else 0
        score += .12 if preview.get("external") else 0
        score += .12 if preview.get("sensitive_data") else 0
        score += .12 if not preview.get("reversible",True) else 0
        score += min(.1,targets*.02)
        level="low" if score<.3 else "medium" if score<.55 else "high" if score<.8 else "critical"
        return {"score":round(_clip(score),4),"level":level,"target_count":targets,"external":bool(preview.get("external")),"reversible":bool(preview.get("reversible",True))}

class ActionRiskScorer:
    def score(self,preview:dict[str,Any],blast:dict[str,Any],*,cost_estimate:float=0.0,evidence_quality:float=.5)->dict[str,Any]:
        effects=set(preview.get("effects",[])); risk=.35*float(blast["score"])
        risk += .2 if "delete" in effects or preview.get("destructive") else 0
        risk += .15 if not preview.get("reversible",True) else 0
        risk += .12 if preview.get("sensitive_data") else 0
        risk += .08 if preview.get("communicates") else 0
        risk += .08 if preview.get("spends_money") or cost_estimate>0 else 0
        risk += min(.12,max(0.0,float(cost_estimate))/1000*.12)
        risk += .1*(1-_clip(evidence_quality))
        return {"risk":round(_clip(risk),4),"level":"low" if risk<.3 else "medium" if risk<.55 else "high" if risk<.8 else "critical","evidence_quality":round(_clip(evidence_quality),4),"cost_estimate":round(max(0,float(cost_estimate)),4)}

class AdaptiveApprovalThreshold:
    def decide(self,risk:dict[str,Any],preview:dict[str,Any],*,autonomy_percent:int=50,approved:bool=False)->dict[str,Any]:
        r=float(risk["risk"]); autonomy=_clip(autonomy_percent/100)
        effects=set(preview.get("effects",[]))
        # Money is never an autonomous side effect. Any purchase, prepaid credit,
        # subscription or paid upgrade requires a separate human approval.
        if "spend" in effects or preview.get("spends_money"):
            return {"decision":"APPROVED" if approved else "REQUIRE_APPROVAL","threshold":0.0,"requires_human":not approved,"reason":"spend_always_requires_human"}
        auto_threshold=.22+.30*autonomy
        if preview.get("destructive") or not preview.get("reversible",True): auto_threshold=min(auto_threshold,.24)
        if r>=.9: return {"decision":"DENY" if not approved else "APPROVED","threshold":round(auto_threshold,4),"requires_human":True,"reason":"critical_risk"}
        if r>auto_threshold:
            return {"decision":"APPROVED" if approved else "REQUIRE_APPROVAL","threshold":round(auto_threshold,4),"requires_human":not approved,"reason":"risk_above_autonomy_threshold"}
        return {"decision":"AUTO_APPROVE","threshold":round(auto_threshold,4),"requires_human":False,"reason":"within_autonomy_threshold"}

class DryRunEngine:
    def run(self,preview:dict[str,Any],risk:dict[str,Any],approval:dict[str,Any])->dict[str,Any]:
        return {"dry_run":True,"executed":False,"preview":preview,"risk":risk,"approval":approval}

class ExactlyOnceExternalActionModel:
    KEY="external_action_once_v2"
    _lock=threading.RLock()
    def begin(self,state:ProjectState,*,key:str,operation:str,preview_digest:str)->dict[str,Any]:
        if not key: raise ValueError("idempotency key required")
        with self._lock:
            rows=state.metadata.setdefault(self.KEY,{})
            if key in rows:
                rows[key]["attempts"]=int(rows[key].get("attempts",1))+1
                return {"execute":False,"record":copy.deepcopy(rows[key]),"reason":"duplicate_key"}
            rows[key]={"operation":operation,"status":"prepared","preview_digest":preview_digest,"attempts":1,"committed_count":0}
            return {"execute":True,"record":copy.deepcopy(rows[key]),"reason":"new_key"}
    def commit(self,state:ProjectState,key:str,result:Any)->None:
        with self._lock:
            row=state.metadata[self.KEY][key]; row["status"]="committed"; row["result_digest"]=_digest(result); row["committed_count"]=int(row.get("committed_count",0))+1
    def fail(self,state:ProjectState,key:str,*,retryable:bool)->None:
        with self._lock:
            row=state.metadata[self.KEY][key]; row["status"]="retryable_failure" if retryable else "failed"
    def reconcile(self,state:ProjectState)->list[str]:
        with self._lock:
            pending=[]
            for k,row in state.metadata.setdefault(self.KEY,{}).items():
                if row.get("status") in {"prepared","executing"}: row["status"]="needs_reconciliation"; pending.append(k)
            return pending

class IntegrityEngineeringCore:
    VERSION=1
    def __init__(self):
        self.hotspots=CodeHotspotDetector(); self.debt=TechnicalDebtLedger(); self.debt_priority=DebtPrioritizer(); self.refactor=RefactorSafetyHarness(); self.architecture=ArchitectureDriftDetector(); self.contracts=InterfaceContractVerifier(); self.state_machine=StateMachineVerifier(); self.properties=PropertyTestEngine(); self.fuzzer=InputFuzzer(); self.concurrency=ConcurrencyFuzzer(); self.crash=CrashInjector(); self.recovery_oracle=CrashRecoveryOracle(); self.transactions=TransactionalProjectState(); self.side_effects=SideEffectRegistry(); self.preview=ActionPreviewEngine(); self.blast=BlastRadiusEstimator(); self.risk=ActionRiskScorer(); self.approval=AdaptiveApprovalThreshold(); self.dry_run=DryRunEngine(); self.exactly_once=ExactlyOnceExternalActionModel()
    def preflight(self,state:ProjectState,*,tool:str,tool_row:dict[str,Any],kwargs:dict[str,Any]|None=None,cost_estimate:float=0.0,evidence_quality:float=.5,approved:bool=False)->dict[str,Any]:
        definition=self.side_effects.get(state,tool,fallback=tool_row); preview=self.preview.preview(definition,kwargs); blast=self.blast.estimate(preview); risk=self.risk.score(preview,blast,cost_estimate=cost_estimate,evidence_quality=evidence_quality); approval=self.approval.decide(risk,preview,autonomy_percent=int(state.metadata.get("autonomy_profile_percent",50) or 50),approved=approved)
        return {"preview":preview,"blast_radius":blast,"risk":risk,"approval":approval}
    def snapshot(self,state:ProjectState)->dict[str,Any]:
        debt=self.debt.open_items(state); return {"integrity_engineering_version":self.VERSION,"open_debt":len(debt),"debt_top":self.debt_priority.prioritize(debt)[:10],"side_effect_tools":len(state.metadata.get(SideEffectRegistry.KEY,{})),"external_action_records":len(state.metadata.get(ExactlyOnceExternalActionModel.KEY,{})),"state_machine":self.state_machine.audit_project(state)}
