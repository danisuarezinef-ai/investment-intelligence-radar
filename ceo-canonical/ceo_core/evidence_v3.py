from __future__ import annotations
from dataclasses import dataclass,asdict
from .models import ProjectState

@dataclass(slots=True)
class ClaimEvidence:
    claim_id:str
    source_id:str
    primary:bool=False
    independent:bool=True
    current:bool=True
    reproducible:bool=False
    methodological_quality:float=.5

class ClaimLevelVerifier:
    def priority(self,claim:dict)->float:
        return min(1.0,.35*float(claim.get('importance',.5))+.35*float(claim.get('risk',.5))+.3*(1-float(claim.get('confidence',.5))))
    def verification_depth(self,claim:dict)->int:
        p=self.priority(claim);return 4 if p>.8 else 3 if p>.6 else 2 if p>.35 else 1
    def plan(self,claim:dict)->list[str]:
        depth=self.verification_depth(claim);text=str(claim.get('text','claim'))
        steps=[f'Check primary support for: {text}']
        if depth>=2:steps.append(f'Find independent corroboration for: {text}')
        if depth>=3:steps.append(f'Attempt adversarial refutation of: {text}')
        if depth>=4:steps.append(f'Reconcile methodological and source-level disagreements for: {text}')
        return steps

class EvidenceWeightingEngine:
    def score(self,evidences:list[ClaimEvidence])->float:
        if not evidences:return 0.0
        vals=[]
        groups=set()
        for e in evidences:
            v=.25+.2*e.primary+.15*e.independent+.1*e.current+.1*e.reproducible+.2*max(0,min(1,e.methodological_quality));vals.append(v)
            if e.independent:groups.add(e.source_id)
        independence=min(1.0,len(groups)/max(1,len(evidences)))
        return round(min(1.0,sum(vals)/len(vals)*(.75+.25*independence)),4)
