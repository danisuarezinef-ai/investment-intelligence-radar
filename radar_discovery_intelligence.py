"""Discovery/Data Intelligence v2: schemas and conservative scoring for early signals."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

def clamp(x,a=0,b=1):return max(a,min(b,float(x)))
@dataclass
class DataPoint:
    value:object; source:str; observed_at:str; known_at:str; retrieved_at:str
    quality:float; discrepancy:float=0.; stale:float=0.; point_in_time:bool=True
    def score(self):return clamp(self.quality)*(1-.5*clamp(self.discrepancy))*(1-.5*clamp(self.stale))*(1 if self.point_in_time else .55)

def surprise(actual, expected, scale):
    if not scale:return 0.0
    return max(-5,min(5,(float(actual)-float(expected))/abs(float(scale))))

def investable_discovery(importance, novelty, priced_in, evidence_quality, causal_reach, liquidity=1):
    """Important != investable. High priced-in fraction explicitly destroys discovery value."""
    return clamp(importance)*clamp(novelty)*(1-clamp(priced_in))*clamp(evidence_quality)*(0.5+0.5*clamp(causal_reach))*clamp(liquidity)

SIGNAL_FAMILIES={
 'hiring_acceleration':['job postings','specialist hiring','geographic expansion'],
 'science_to_industry':['papers','clinical/engineering milestones','licensing'],
 'patent_acceleration':['filings','citations','assignee changes'],
 'capex_supply_chain':['capex','orders','lead times','capacity'],
 'regulatory_change':['rules','approvals','subsidies','restrictions'],
 'public_contracts':['awards','tenders','backlog'],
 'language_change':['earnings language','risk factors','guidance'],
 'bottlenecks':['power','grid','transformers','minerals','packaging','logistics'],
}

SOURCE_MAP={
 'market':['prices','volume','volatility','corporate actions'],
 'fundamentals':['filings','earnings','balance sheet','cash flow','valuation'],
 'macro':['rates','inflation','employment','credit','liquidity'],
 'science':['papers','trials','engineering milestones'],
 'innovation':['patents','licenses','standards'],
 'regulation':['laws','rules','approvals','sanctions','subsidies'],
 'industry':['capacity','capex','orders','inventory','lead times'],
 'geopolitics':['trade controls','conflict','alliances','supply concentration'],
 'alternative':['hiring','contracts','web/product signals'],
}

def second_third_order(seed,graph,max_depth=3):
    paths=[]
    def walk(node,path,depth):
        if depth>=max_depth:return
        for nxt in graph.get(node,[]):
            if nxt in path:continue
            p=path+[nxt];paths.append(p);walk(nxt,p,depth+1)
    walk(seed,[seed],0);return paths
