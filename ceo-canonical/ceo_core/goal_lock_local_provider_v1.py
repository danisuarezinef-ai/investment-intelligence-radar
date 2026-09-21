from __future__ import annotations
from .contracts import WorkerKind,WorkerProvider,WorkerRequest,WorkerResult
from .models import Task

class GoalLockLocalProviderV1(WorkerProvider):
    """Deterministic zero-network worker for the baseline goal-lock phase."""
    name='ceo-local-goal-lock'
    kind=WorkerKind.LOCAL
    capabilities=frozenset({'general','reasoning'})
    def supports(self,task:Task)->bool:
        return bool(task.metadata.get('local_fallback_kind')=='goal_lock' or str(task.title).lower().startswith('clarify & lock goal'))
    async def execute(self,request:WorkerRequest)->WorkerResult:
        g=request.goal
        constraints='; '.join(g.constraints) if g.constraints else 'No additional constraints declared.'
        criteria='; '.join(g.completion_criteria) if g.completion_criteria else 'Completion requires concrete verified output.'
        deliverables='; '.join(g.deliverables) if g.deliverables else 'Deliverables are derived from the stated objective.'
        text=(
            'Goal locked deterministically from the durable project contract. '
            f'Objective: {g.objective}. Definition: {g.definition or g.objective}. '
            f'Constraints: {constraints} Completion criteria: {criteria} Deliverables: {deliverables} '
            'No external provider, purchase, publication, credential change, or irreversible action was required for this goal-lock step.'
        )
        return WorkerResult(provider=self.name,kind=self.kind,success=True,text=text,metadata={'local_goal_lock':True,'network_used':False,'spending_attempts':0})
