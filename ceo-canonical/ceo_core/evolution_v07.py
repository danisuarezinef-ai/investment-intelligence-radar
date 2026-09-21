from __future__ import annotations
from dataclasses import asdict
from .models import ProjectState,TaskStatus
from .meta_planning import MetaPlanningEngine,PlanCandidate
from .objective_governance import GoalDriftDetector,ConstitutionEnforcer
from .directors_v2 import HierarchicalDirectorV2,TeamReorganizer,DelegationEngine
from .knowledge_graph import GlobalKnowledgeGraph,UncertaintyPropagationEngine,ActiveLearningEngine,DeepResearchController
from .human_escalation import NotificationIntelligence
from .project_replay import AutonomousRetrospective

class StrategicEvolutionLoopV07:
    """Strategic supervisor layered above the 0.6 autonomous loop.

    It intentionally writes derived state to metadata so ProjectState schema remains
    backward compatible. New projects enable it with metadata['enable_v07']=True.
    """
    def __init__(self)->None:
        self.meta=MetaPlanningEngine();self.drift=GoalDriftDetector();self.constitution=ConstitutionEnforcer();self.directors=HierarchicalDirectorV2();self.teams=TeamReorganizer();self.delegate=DelegationEngine();self.kg=GlobalKnowledgeGraph();self.uncertainty=UncertaintyPropagationEngine();self.active=ActiveLearningEngine();self.deep=DeepResearchController();self.notify=NotificationIntelligence();self.retro=AutonomousRetrospective()
    def tick(self,state:ProjectState)->dict:
        if not state.metadata.get('enable_v07'):
            return {'enabled':False}
        if 'meta_plan' not in state.metadata:
            self.meta.choose(state,[
                PlanCandidate('balanced',.15,3600,.82,.18,.7,.7),
                PlanCandidate('fast',.08,1800,.70,.25,.5,.4),
                PlanCandidate('deep',.35,7200,.93,.12,.9,.95),
            ])
        drift=self.drift.inspect(state)
        constitution_violations={}
        for t in state.leaf_tasks:
            violations=self.constitution.violations(state,t)
            if violations:
                constitution_violations[t.id]=violations
                t.metadata['constitution_violations']=violations
        tree=self.directors.build(state,team_size=int(state.metadata.get('v07_team_size',24)))
        self.teams.rebalance(state,max_team=int(state.metadata.get('v07_max_team',32)))
        for t in state.leaf_tasks:
            if t.status in {TaskStatus.READY,TaskStatus.WAITING,TaskStatus.RETRY}:
                t.metadata.setdefault('delegation_strategy',self.delegate.strategy(t))
        # Mirror task/claim/source relationships into the graph without raw conversation text.
        for t in state.tasks.values():
            self.kg.add_node(state,f'task:{t.id}','task',t.title,status=t.status.value)
            if t.parent_id:self.kg.add_edge(state,f'task:{t.id}',f'task:{t.parent_id}','depends_on',.5)
        for cid,c in state.metadata.get('claims',{}).items():
            self.kg.add_node(state,f'claim:{cid}','claim',str(c.get('text',''))[:240],confidence=float(c.get('confidence',.5)))
            for tid in c.get('task_ids',[]) or []:self.kg.add_edge(state,f'claim:{cid}',f'task:{tid}','derived_from',1.0)
        uncertainty={f"claim:{cid}":1-float(c.get('confidence',.5)) for cid,c in state.metadata.get('claims',{}).items()}
        propagated=self.uncertainty.propagate(state,uncertainty) if uncertainty else {}
        active_candidates=[t for t in state.leaf_tasks if t.status in {TaskStatus.READY,TaskStatus.WAITING,TaskStatus.RETRY}]
        next_info=self.active.choose(active_candidates)
        deep_candidates=[t.id for t in active_candidates if self.deep.should_enter(t)]
        out={'enabled':True,'drift_count':len(drift),'constitution_violations':len(constitution_violations),'directors':len(tree),'knowledge_nodes':len(state.metadata.get('knowledge_graph',{}).get('nodes',{})),'uncertainty_nodes':len(propagated),'highest_information_task':next_info.id if next_info else None,'deep_research_candidates':deep_candidates[:25]}
        state.metadata['strategic_loop_v07']=out
        return out
    def finalize(self,state:ProjectState)->dict:
        return self.retro.evaluate(state)
