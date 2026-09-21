from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from typing import Any

from .models import ProjectState, Task, TaskStatus


class ContextCompressor:
    def compress(self,text:str,max_chars:int=7000)->str:
        text=(text or '').strip()
        if len(text)<=max_chars:return text
        head=text[:int(max_chars*.55)];tail=text[-int(max_chars*.30):]
        return head+"\n...[context compressed]...\n"+tail
    def fingerprint(self,text:str)->str:return sha256((text or '').encode()).hexdigest()[:16]


class SemanticContextRetriever:
    @staticmethod
    def tokens(text:str)->set[str]:return {x.lower().strip('.,:;!?()[]{}') for x in text.split() if len(x)>2}
    def score(self,query:str,text:str)->float:
        q,t=self.tokens(query),self.tokens(text)
        return len(q&t)/len(q|t) if q and t else 0.0
    def retrieve(self,state:ProjectState,query:str,k:int=8)->list[dict[str,Any]]:
        rows=[]
        for tid,item in state.metadata.get('knowledge',{}).items():
            text=f"{item.get('title','')} {item.get('result','')}";score=self.score(query,text)
            if score>0:rows.append((score,tid,item))
        rows.sort(reverse=True,key=lambda x:x[0])
        return [{"task_id":tid,"score":round(score,4),"title":item.get('title'),"result":item.get('result')} for score,tid,item in rows[:k]]


class HierarchicalSummarizer:
    def update(self,state:ProjectState)->dict[str,str]:
        summaries={}
        for rid in state.root_task_ids:
            root=state.tasks.get(rid)
            if not root:continue
            facts=[];openq=[];sources=[];uncertainties=[];decisions=[]
            for cid in root.children:
                t=state.tasks.get(cid)
                if not t:continue
                if t.result:facts.append(f"{t.title}: {t.result[:500]}")
                if t.status in {TaskStatus.FAILED,TaskStatus.NEEDS_REVIEW,TaskStatus.BLOCKED}:openq.append(t.title)
                if t.status in {TaskStatus.PARTIAL_COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY} or (t.confidence is not None and t.confidence<.6):uncertainties.append(t.title)
                if t.metadata.get('decision_id'):decisions.append(f"{t.title}: {t.metadata.get('decision_id')}")
                sources.extend(str(x) for x in t.metadata.get('sources',[]))
            summaries[rid]="FACTS:\n"+"\n".join(facts[:30])+"\nDECISIONS:\n"+"\n".join(decisions[:20])+"\nUNCERTAINTIES:\n"+"\n".join(uncertainties[:20])+"\nOPEN:\n"+"\n".join(openq[:20])+"\nSOURCES:\n"+"\n".join(sources[:30])
        state.metadata['project_summaries']=summaries
        state.metadata['project_summary']='\n\n'.join(summaries.values())[:30000]
        return summaries


@dataclass(slots=True)
class CompressionCheck:
    retained:float;critical_missing:list[str]


class CompressionValidator:
    def validate(self,original:str,compressed:str,critical_terms:list[str]|None=None)->CompressionCheck:
        critical_terms=critical_terms or []
        retained=SequenceMatcher(None,original[:12000],compressed[:12000]).ratio() if original else 1.0
        missing=[x for x in critical_terms if x.lower() not in compressed.lower()]
        return CompressionCheck(round(retained,4),missing)


class MemoryGarbageCollector:
    def collect(self,state:ProjectState)->dict[str,int]:
        knowledge=state.metadata.get('knowledge',{});seen={};removed=0
        for tid in list(knowledge):
            digest=knowledge[tid].get('digest')
            if digest and digest in seen:
                knowledge.pop(tid,None);removed+=1
            elif digest:seen[digest]=tid
        order=state.metadata.get('result_order',[]);state.metadata['result_order']=[x for x in order if x in knowledge]
        return {'knowledge_duplicates_removed':removed}


class ContextBuilder:
    def __init__(self,compressor:ContextCompressor|None=None)->None:
        self.compressor=compressor or ContextCompressor();self.retriever=SemanticContextRetriever();self.validator=CompressionValidator()
    def build(self,state:ProjectState,task:Task)->dict:
        deps=[]
        for dep_id in task.dependencies:
            dep=state.tasks.get(dep_id)
            if dep and dep.result:deps.append({'task':dep.title,'result':self.compressor.compress(dep.result,2500)})
        parent=state.tasks.get(task.parent_id) if task.parent_id else None;siblings=[]
        if parent:
            for sid in parent.children:
                if sid==task.id:continue
                s=state.tasks.get(sid)
                if s and s.result and s.status in {TaskStatus.COMPLETE,TaskStatus.COMPLETE_WITH_UNCERTAINTY}:
                    siblings.append({'task':s.title,'result':self.compressor.compress(s.result,1200)})
                if len(siblings)>=5:break
        semantic=self.retriever.retrieve(state,f"{task.title} {task.description}",k=6)
        original=str(state.metadata.get('project_summary',''));compressed=self.compressor.compress(original,3000)
        check=self.validator.validate(original,compressed,list(state.metadata.get('critical_context_terms',[])))
        state.metadata['context_integrity']={'retained':check.retained,'critical_missing':check.critical_missing}
        return {'dependencies':deps,'relevant_siblings':siblings,'semantic_memory':semantic,'project_preferences':state.metadata.get('preferences',{}),'knowledge_summary':compressed}
