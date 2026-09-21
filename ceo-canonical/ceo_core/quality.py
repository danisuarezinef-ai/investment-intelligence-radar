from __future__ import annotations

from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Iterable, Any

from .claims import ClaimExtractor, ClaimRegistry, SourceRegistry
from .models import ProjectState, Task, TaskStatus


@dataclass(slots=True)
class QualityAssessment:
    confidence: float
    quality: float
    evidence_strength: float
    source_quality: float
    consensus: float
    verification_depth: float
    needs_review: bool
    reasons: list[str]


class QualityEngine:
    """Separates answer quality, confidence, evidence, source quality, consensus and verification."""
    def assess(self,task:Task,*,agreement:float|None=None,source_count:int|None=None,source_quality:float|None=None,independent_sources:int|None=None,verification_depth:float|None=None)->QualityAssessment:
        reasons=[];base=.50
        if task.result and len(task.result.strip())>=80:base+=.08
        else:reasons.append("result_too_short")
        if task.acceptance_criteria:base+=min(.12,.03*len(task.acceptance_criteria))
        failures=int(task.metadata.get("failure_count",0));base-=min(.20,.05*failures)
        if failures:reasons.append("provider_failures")
        verification=float(verification_depth if verification_depth is not None else task.metadata.get("verification_depth",1.0 if task.metadata.get("verified") else 0.0))
        verification=max(0,min(1,verification));cons=max(0,min(1,agreement if agreement is not None else float(task.metadata.get("consensus",.5))))
        sq=max(0,min(1,source_quality if source_quality is not None else float(task.metadata.get("source_quality",.5))))
        independent=int(independent_sources if independent_sources is not None else task.metadata.get("independent_source_count",source_count or 0))
        evidence=min(1.0,.25+.15*min(4,independent)+.25*verification)
        quality=max(0,min(1,base*.45+sq*.18+cons*.17+evidence*.20))
        confidence=max(0,min(1,quality*.55+evidence*.25+cons*.20))
        threshold=float(task.metadata.get("quality_threshold",.62))
        if independent==0 and (source_count or 0)>0:reasons.append("source_independence_unknown")
        return QualityAssessment(round(confidence,4),round(quality,4),round(evidence,4),round(sq,4),round(cons,4),round(verification,4),quality<threshold,reasons)


class ResultIntegrator:
    def __init__(self)->None:
        self.claims=ClaimRegistry();self.sources=SourceRegistry();self.extractor=ClaimExtractor()
    def integrate_task(self,state:ProjectState,task:Task)->None:
        if not task.result:return
        knowledge=state.metadata.setdefault("knowledge",{});digest=sha256(task.result.encode("utf-8",errors="ignore")).hexdigest()
        claim_ids=self.extractor.ingest_task(state,task,self.claims,self.sources)
        knowledge[task.id]={"title":task.title,"result":task.result,"confidence":task.confidence,"quality":task.quality_score,"provider":task.provider_name,"digest":digest,"parent_id":task.parent_id,"claim_ids":claim_ids}
        order=state.metadata.setdefault("result_order",[])
        if task.id not in order:order.append(task.id)
        # Novelty used by the marginal-yield completion logic.
        prior=[knowledge[x].get("digest") for x in order[:-1] if x in knowledge]
        task.metadata["novelty"]=0.0 if digest in prior else 1.0
    def summary(self,state:ProjectState,max_items:int=50)->str:
        knowledge=state.metadata.get("knowledge",{});order=state.metadata.get("result_order",[])[-max_items:];chunks=[]
        for tid in order:
            item=knowledge.get(tid)
            if item:
                text=str(item.get("result","")).strip().replace("\n"," ");chunks.append(f"- {item.get('title')}: {text[:500]}")
        return "\n".join(chunks)


class ConflictResolver:
    NEGATIONS=(("yes","no"),("supports","does not support"),("valid","invalid"),("true","false"),("increase","decrease"))
    def similarity(self,a:str,b:str)->float:return SequenceMatcher(None,a.lower(),b.lower()).ratio()
    def classify(self,a:Task,b:Task)->str:
        ma,mb=a.metadata,b.metadata
        if ma.get("source_ids")!=mb.get("source_ids") and ma.get("method")!=mb.get("method"):return "methodological"
        if ma.get("source_ids")!=mb.get("source_ids"):return "source"
        if ma.get("interpretation") or mb.get("interpretation"):return "interpretive"
        return "factual"
    def conflicts(self,a:Task,b:Task)->bool:
        if not a.result or not b.result or self.similarity(a.title,b.title)<.5:return False
        la,lb=a.result.lower(),b.result.lower()
        return any((x in la and y in lb) or (y in la and x in lb) for x,y in self.NEGATIONS)
    def find_conflicts(self,state:ProjectState)->list[tuple[str,str]]:
        done=[t for t in state.leaf_tasks if t.status in {TaskStatus.COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY} and t.result];out=[]
        for i,a in enumerate(done):
            for b in done[i+1:]:
                if self.conflicts(a,b):out.append((a.id,b.id))
        return out


class ConsensusBuilder:
    """Consensus counts independent evidence groups rather than raw agent votes."""
    def build(self,state:ProjectState,tasks:Iterable[Task])->dict[str,Any]:
        tasks=[t for t in tasks if t.result];groups:dict[str,list[Task]]={}
        for t in tasks:
            source_groups=tuple(sorted(set(t.metadata.get("independent_source_groups",[]))))
            key="|".join(source_groups) if source_groups else f"worker:{t.provider_name or t.id}"
            groups.setdefault(key,[]).append(t)
        reps=[rows[0] for rows in groups.values()]
        if not reps:return {"consensus":0.0,"independent_groups":0,"representatives":[]}
        # Similarity-based agreement over independent representatives.
        sims=[]
        for i,a in enumerate(reps):
            for b in reps[i+1:]:sims.append(SequenceMatcher(None,(a.result or '').lower(),(b.result or '').lower()).ratio())
        consensus=sum(sims)/len(sims) if sims else 1.0
        return {"consensus":round(consensus,4),"independent_groups":len(groups),"representatives":[t.id for t in reps]}


class AdversarialVerifier:
    def build_task(self,target:Task)->Task:
        return Task(title=f"Adversarial check: {target.title}",description="Try to falsify the target conclusion. Seek counterexamples, unsupported assumptions, circular sourcing and alternative explanations.",priority=min(100,target.priority+12),dependencies=[target.id],required_capabilities=list(target.required_capabilities),acceptance_criteria=["Attempted falsification","Counterevidence documented","Verdict returned"],metadata={"verification_task":True,"adversarial":True,"verifies":target.id,"avoid_providers":[target.provider_name] if target.provider_name else []})


class SemanticDeduplicator:
    @staticmethod
    def _tokens(text:str)->set[str]:return {w.strip(".,:;!?()[]{}\\\"'").lower() for w in text.split() if len(w)>2}
    def score(self,a:str,b:str)->float:
        x,y=self._tokens(a),self._tokens(b)
        return len(x&y)/len(x|y) if x and y else 0.0
    def find_duplicate(self,task:Task,candidates:Iterable[Task],threshold:float=.82)->Task|None:
        text=f"{task.title} {task.description}"
        for other in candidates:
            if other.id!=task.id and self.score(text,f"{other.title} {other.description}")>=threshold:return other
        return None
