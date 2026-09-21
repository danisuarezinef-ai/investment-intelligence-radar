from __future__ import annotations
from dataclasses import dataclass,asdict
from .models import ProjectState,Task,TaskStatus
from .task_roles_v2 import is_productive
from .blocked_safe_state_v1 import is_blocked_safe
@dataclass(slots=True)
class StallReplanResult:
    action:str; requeued:int; superseded:int; replacements:int; bounded:bool
    def to_dict(self):return asdict(self)
class ProductivityStallReplannerV2:
    KEY='productivity_stall_replanner_v2'
    def repair(self,state:ProjectState,*,max_generation:int=3)->StallReplanResult:
        requeued=superseded=replacements=0
        stalled=[t for t in state.leaf_tasks if is_productive(t,state) and t.status in {TaskStatus.BLOCKED,TaskStatus.FAILED,TaskStatus.NEEDS_REVIEW} and not is_blocked_safe(t)]
        for t in stalled:
            gen=int(t.metadata.get('stall_replan_generation',0))
            if gen>=max_generation: continue
            if t.status==TaskStatus.NEEDS_REVIEW and t.metadata.get('explicit_human_gate'): continue
            if t.attempts<t.max_attempts:
                t.status=TaskStatus.RETRY;t.metadata['stall_replan_generation']=gen+1;requeued+=1
            else:
                alt=Task(title=f'Replan: {t.title}',description=t.description,status=TaskStatus.READY,priority=t.priority,dependencies=list(t.dependencies),estimated_seconds=t.estimated_seconds,metadata={**t.metadata,'stall_replan_generation':gen+1,'replanned_from':t.id,'task_role':'productive'})
                state.tasks[alt.id]=alt;state.root_task_ids.append(alt.id)
                # Preserve the DAG: descendants that depended on the exhausted task
                # must follow the replacement, otherwise a successful replan can still
                # strand the entire mission behind a superseded ID.
                for other in state.tasks.values():
                    if other.id == alt.id or t.id not in other.dependencies:
                        continue
                    other.dependencies = [alt.id if dep == t.id else dep for dep in other.dependencies]
                    other.metadata['dependency_rewired_from'] = t.id
                    other.metadata['dependency_rewired_to'] = alt.id
                # DEV275: when the exhausted task is a child, replacing only DAG
                # dependencies is insufficient: the phase/group parent would still
                # wait forever on the superseded child ID. Replace that membership too.
                if t.parent_id and t.parent_id in state.tasks:
                    parent=state.tasks[t.parent_id]
                    parent.children=[alt.id if child_id==t.id else child_id for child_id in parent.children]
                    alt.parent_id=t.parent_id
                else:
                    state.root_task_ids=[alt.id if rid==t.id else rid for rid in state.root_task_ids]
                t.status=TaskStatus.SUPERSEDED;t.metadata['replacement_task_id']=alt.id;superseded+=1;replacements+=1
        bounded=all(int(t.metadata.get('stall_replan_generation',0))>=max_generation for t in stalled if t.status not in {TaskStatus.RETRY,TaskStatus.SUPERSEDED}) if stalled else False
        out=StallReplanResult('replanned' if (requeued or replacements) else 'bounded_or_noop',requeued,superseded,replacements,bounded)
        state.metadata[self.KEY]=out.to_dict();return out
