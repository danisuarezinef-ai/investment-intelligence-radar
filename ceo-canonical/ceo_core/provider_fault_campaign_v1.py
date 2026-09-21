from __future__ import annotations
from dataclasses import dataclass,asdict
from .provider_resilience_v2 import ProviderResilienceV2
@dataclass(slots=True)
class FaultCampaignResult:
    cases:int; safe_retries:int; human_gates:int; spending_attempts:int; violations:int
    def to_dict(self):return asdict(self)
class ProviderFaultCampaignV1:
    CASES=['HTTP 429 RESOURCE_EXHAUSTED quota','HTTP 503 temporarily unavailable','timeout','HTTP 404 model unavailable','HTTP 401 unauthorized','billing required','connection reset']
    def run(self)->FaultCampaignResult:
        p=ProviderResilienceV2();safe=human=spend=viol=0
        for i,e in enumerate(self.CASES,1):
            d=p.classify(e,i)
            safe+=int(d.retry);human+=int(d.requires_human);spend+=int(d.spending_allowed)
            if d.spending_allowed:viol+=1
            if ('401' in e or 'billing' in e) and not d.requires_human:viol+=1
        return FaultCampaignResult(len(self.CASES),safe,human,spend,viol)
