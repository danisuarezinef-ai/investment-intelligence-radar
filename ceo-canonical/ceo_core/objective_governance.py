from __future__ import annotations
from dataclasses import dataclass,asdict,field
from difflib import SequenceMatcher
from .models import ProjectState,Task

@dataclass(slots=True)
class ProjectConstitution:
    immutable_rules:list[str]=field(default_factory=list)
    allowed_sources:list[str]=field(default_factory=list)
    prohibited_actions:list[str]=field(default_factory=list)
    max_budget:float|None=None
    min_quality:float=.0
    confidentiality:str='private'
    completion_rules:list[str]=field(default_factory=list)

class ObjectiveNegotiator:
    CRITICAL=(('objective','What exact outcome should CEO deliver?'),('completion','What must be true for the project to count as complete?'))
    def missing_questions(self,objective:str,completion_criteria:list[str],constraints:list[str])->list[str]:
        out=[]
        if len(objective.strip())<12:out.append(self.CRITICAL[0][1])
        if not completion_criteria:out.append(self.CRITICAL[1][1])
        if not constraints:out.append('Are there any hard constraints, forbidden actions, sources, or budget limits?')
        return out
    def contract(self,state:ProjectState,const:ProjectConstitution)->dict:
        state.metadata['project_constitution']=asdict(const)
        if const.max_budget is not None:state.budget_limit=const.max_budget
        return state.metadata['project_constitution']
    def apply_answers(self,state:ProjectState,*,objective:str|None=None,definition:str|None=None,completion:list[str]|None=None,constraints:list[str]|None=None)->ProjectState:
        if objective is not None: state.goal=objective.strip()
        if definition is not None: state.goal_definition=definition.strip()
        if completion is not None: state.completion_criteria=[x.strip() for x in completion if x.strip()]
        if constraints is not None: state.goal_constraints=[x.strip() for x in constraints if x.strip()]
        state.metadata['goal_contract_locked']=not bool(self.missing_questions(state.goal,state.completion_criteria,state.goal_constraints))
        return state

class ConstitutionEnforcer:
    def violations(self,state:ProjectState,task:Task)->list[str]:
        c=state.metadata.get('project_constitution',{});out=[]
        action=str(task.metadata.get('action','')).lower()
        for forbidden in c.get('prohibited_actions',[]) or []:
            if str(forbidden).lower() in action:out.append(f'prohibited_action:{forbidden}')
        max_budget=c.get('max_budget')
        if max_budget is not None and float(task.cost_estimate or 0)>float(max_budget):out.append('task_cost_exceeds_project_budget')
        min_q=float(c.get('min_quality',0) or 0)
        if task.quality_score is not None and float(task.quality_score)<min_q:out.append('quality_below_constitution')
        return out

class GoalDriftDetector:
    def task_alignment(self,state:ProjectState,task:Task)->float:
        goal=' '.join([state.goal,state.goal_definition,*state.completion_criteria]).lower()
        text=' '.join([task.title,task.description,*task.acceptance_criteria]).lower()
        if not goal.strip() or not text.strip():return .0
        goal_tokens=set(goal.split()); task_tokens=set(text.split())
        lexical=len(goal_tokens&task_tokens)/max(1,len(goal_tokens|task_tokens))
        seq=SequenceMatcher(None,goal[:600],text[:600]).ratio()
        return round(.7*lexical+.3*seq,4)
    def inspect(self,state:ProjectState,threshold:float=.08)->list[str]:
        drift=[]
        for t in state.leaf_tasks:
            if not t.metadata.get('explicitly_out_of_scope') and self.task_alignment(state,t)<threshold:drift.append(t.id)
        state.metadata['goal_drift']={'task_ids':drift,'count':len(drift)}
        return drift
