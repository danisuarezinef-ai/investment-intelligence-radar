from __future__ import annotations
from dataclasses import dataclass,asdict
from math import log
from .models import ProjectState,Task

class GlobalKnowledgeGraph:
    def _g(self,state:ProjectState)->dict:
        return state.metadata.setdefault('knowledge_graph',{'nodes':{},'edges':[],'edge_index':{}})
    def add_node(self,state:ProjectState,node_id:str,kind:str,label:str,**attrs)->None:
        self._g(state)['nodes'][node_id]={'id':node_id,'kind':kind,'label':label,**attrs}
    def add_edge(self,state:ProjectState,src:str,dst:str,relation:str,weight:float=1.0)->None:
        g=self._g(state);key=f'{src}|{dst}|{relation}|{float(weight):.6g}'
        index=g.setdefault('edge_index',{})
        if key in index:return
        row={'src':src,'dst':dst,'relation':relation,'weight':float(weight)}
        g['edges'].append(row);index[key]=len(g['edges'])-1
    def neighbors(self,state:ProjectState,node_id:str,relation:str|None=None)->list[str]:
        out=[]
        for e in self._g(state)['edges']:
            if relation and e['relation']!=relation:continue
            if e['src']==node_id:out.append(e['dst'])
            elif e['dst']==node_id:out.append(e['src'])
        return out
    def missing_links(self,state:ProjectState)->list[tuple[str,str]]:
        g=self._g(state);nodes=list(g['nodes']);known={(e['src'],e['dst']) for e in g['edges']}|{(e['dst'],e['src']) for e in g['edges']}
        suggestions=[]
        for a in nodes:
            na=set(self.neighbors(state,a))
            for b in na:
                for c in self.neighbors(state,b):
                    if c!=a and (a,c) not in known:suggestions.append((a,c))
        return list(dict.fromkeys(suggestions))[:200]

class UncertaintyPropagationEngine:
    def propagate(self,state:ProjectState,claim_uncertainty:dict[str,float])->dict[str,float]:
        g=state.metadata.get('knowledge_graph',{'edges':[]});u=dict(claim_uncertainty)
        changed=True;loops=0
        while changed and loops<8:
            changed=False;loops+=1
            for e in g.get('edges',[]):
                if e.get('relation') not in {'depends_on','supports','derived_from'}:continue
                src,dst=e['src'],e['dst'];base=u.get(dst,0.0)*float(e.get('weight',1.0))
                if base>u.get(src,0.0)+1e-6:u[src]=min(1.0,base);changed=True
        state.metadata['propagated_uncertainty']=u
        return u

@dataclass(slots=True)
class Hypothesis:
    id:str;text:str;confidence:float;supporting:list[str];refuting:list[str]

class HypothesisEngine:
    def generate(self,state:ProjectState,topic:str,evidence:list[str],contradictions:list[str])->Hypothesis:
        hid=f'hyp:{abs(hash((topic,tuple(evidence),tuple(contradictions)))):x}'
        conf=max(.1,min(.9,.5+.08*len(evidence)-.12*len(contradictions)))
        h=Hypothesis(hid,f'Hypothesis for {topic}: reconcile observed evidence and contradictions.',conf,list(evidence),list(contradictions))
        state.metadata.setdefault('hypotheses',{})[hid]=asdict(h)
        return h
    def validation_tasks(self,h:Hypothesis)->list[str]:
        return [f'Find independent evidence supporting: {h.text}',f'Attempt to refute: {h.text}']

class ActiveLearningEngine:
    def information_value(self,task:Task)->float:
        uncertainty=float(task.metadata.get('uncertainty',.5));impact=float(task.metadata.get('impact',.5));novelty=float(task.metadata.get('expected_novelty',.5));cost=max(.05,float(task.cost_estimate or .05));return (uncertainty*impact*novelty)/cost
    def choose(self,tasks:list[Task])->Task|None:return max(tasks,key=self.information_value) if tasks else None

class DeepResearchController:
    def should_enter(self,task:Task)->bool:
        return float(task.metadata.get('uncertainty',0))>.65 and (float(task.metadata.get('impact',0))>.55 or float(task.metadata.get('conflict_score',0))>.45)
    def should_stop(self,task:Task)->bool:
        rounds=int(task.metadata.get('research_rounds',0));yield_rate=float(task.metadata.get('marginal_yield',1.0));return rounds>=8 or (rounds>=3 and yield_rate<.08)
