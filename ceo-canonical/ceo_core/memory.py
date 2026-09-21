from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ProjectState
from .continuity import ContinuityManager


def now():return datetime.now(timezone.utc).isoformat()


class JsonMemory:
    def __init__(self,path:str|Path)->None:self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
    def _load(self)->dict[str,Any]:
        try:return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        except Exception:return {}
    def _save(self,data:dict[str,Any])->None:
        tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(self.path)


class ProceduralMemory(JsonMemory):
    STAGES=('experimental','validated','preferred')
    def record(self,key:str,value:dict[str,Any])->None:
        data=self._load();entry=data.setdefault(key,{"versions":[],"stage":"experimental","successes":0,"failures":0});versions=entry.setdefault('versions',[]);versions.append({"version":len(versions)+1,"ts":now(),**value});entry['latest']=value;self._save(data)
    def get(self,key:str)->dict[str,Any]|None:
        row=self._load().get(key)
        if not row:return None
        # Backward-compatible view: latest payload at top level, plus version metadata.
        latest=dict(row.get('latest') or {}) if isinstance(row,dict) else {}
        if isinstance(row,dict): latest.update({k:v for k,v in row.items() if k not in {'latest','versions'}})
        return latest
    def record_outcome(self,key:str,success:bool)->str|None:
        data=self._load();entry=data.get(key)
        if not entry:return None
        field='successes' if success else 'failures';entry[field]=int(entry.get(field,0))+1
        s,f=int(entry.get('successes',0)),int(entry.get('failures',0));stage=entry.get('stage','experimental')
        if stage=='experimental' and s>=3 and s>=f*2:entry['stage']='validated'
        if entry.get('stage')=='validated' and s>=8 and s>=max(1,f)*3:entry['stage']='preferred'
        if f>s and entry.get('stage')=='preferred':entry['stage']='validated'
        self._save(data);return entry.get('stage')


class DecisionLearningMemory(JsonMemory):
    def record(self,*,situation:str,recommendation:str|None,selected:str,source:str,outcome:str|None=None)->None:
        data=self._load();rows=data.setdefault('decisions',[]);rows.append({'ts':now(),'situation':situation,'recommendation':recommendation,'selected':selected,'source':source,'outcome':outcome});self._save(data)
    def preference(self,situation:str)->str|None:
        rows=[r for r in self._load().get('decisions',[]) if r.get('situation')==situation]
        if not rows:return None
        counts={}
        for r in rows:
            weight=1.5 if r.get('outcome') in {'good','success'} else .5 if r.get('outcome') in {'bad','failure'} else 1.0
            counts[str(r.get('selected'))]=counts.get(str(r.get('selected')),0)+weight
        return max(counts,key=counts.get)


class EpisodicMemory(JsonMemory):
    def record_run(self,project_id:str,*,strategy:str,outcome:str,metrics:dict[str,Any])->None:
        data=self._load();rows=data.setdefault('episodes',[]);rows.append({'ts':now(),'project_id':project_id,'strategy':strategy,'outcome':outcome,'metrics':metrics});self._save(data)
    def similar(self,strategy:str,limit:int=10)->list[dict[str,Any]]:
        return [x for x in self._load().get('episodes',[]) if x.get('strategy')==strategy][-limit:]


class ProjectMemory:
    def __init__(self)->None:self.continuity=ContinuityManager()
    def snapshot(self,state:ProjectState)->dict[str,Any]:
        return {'goal':state.goal,'project_name':state.project_name,'constraints':list(state.goal_constraints),'completion_criteria':list(state.completion_criteria),'knowledge':state.metadata.get('knowledge',{}),'claims':state.metadata.get('claims',{}),'sources':state.metadata.get('sources',{}),'decisions':{k:v.model_dump(mode='json') for k,v in state.decisions.items()},'continuity':self.continuity.capture(state,reason='project_memory')}
