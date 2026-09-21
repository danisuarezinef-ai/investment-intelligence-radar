from __future__ import annotations

import asyncio, json, tempfile, time
from pathlib import Path
from ceo_core.models import ProjectState, Task
from ceo_core.providers.scripted_ai import ScriptedAIProvider
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.store import JsonCheckpointStore


async def main():
    with tempfile.TemporaryDirectory() as td:
        state=ProjectState(goal="Autonomy benchmark", power_percent=100)
        for i in range(120):
            t=Task(title=f"Task {i}", description="Complete autonomously", estimated_seconds=.01)
            state.tasks[t.id]=t; state.root_task_ids.append(t.id)
        provider=ScriptedAIProvider(delay_seconds=.001)
        sched=ContinuousScheduler(state,provider,JsonCheckpointStore(Path(td)/"state.json"))
        started=time.perf_counter();sched.start();await sched._runner
        elapsed=time.perf_counter()-started
        result={"tasks":120,"completed":len(state.completed_leaf_tasks),"elapsed_seconds":round(elapsed,4),"human_interventions":state.human_interventions_required,"avoided":state.human_interventions_avoided}
        print(json.dumps(result,indent=2))
if __name__=="__main__": asyncio.run(main())
