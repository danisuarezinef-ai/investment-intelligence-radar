from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from ceo_core.models import ProjectState,Task
from ceo_core.provider_factory import build_providers
from ceo_core.routing import MultiProviderRouter
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.sqlite_store import SqliteCheckpointStore
from ceo_core.resource_governor import ResourceGovernor
from ceo_core.runtime import bundle_root,user_data_root
from ceo_core.validation import ValidationEvidence,ValidationRegistry,StrictReleaseGates


async def main():
    root=bundle_root();data=user_data_root();data.mkdir(parents=True,exist_ok=True)
    providers=build_providers(root,data)
    real=[p for p in providers if p.name!='mock']
    if not real:
        raise SystemExit('No real provider configured. Configure an API key or an authenticated browser provider; no live validation was recorded.')
    state=ProjectState(goal='Live autonomy validation',goal_definition='Complete a real two-or-more-turn AI conversation without human continue.',completion_criteria=['Return CEO_LIVE_VALIDATED after at least two turns'],power_percent=20)
    task=Task(title='Live multi-turn test',description='On the first turn, analyze the validation task and explicitly continue once. On the second turn, finish and include the marker CEO_LIVE_VALIDATED. Follow the CEO_RESULT protocol exactly.',acceptance_criteria=['At least two conversation turns','Final marker CEO_LIVE_VALIDATED'],estimated_seconds=5)
    state.tasks[task.id]=task;state.root_task_ids=[task.id]
    store=SqliteCheckpointStore(data/'live_validation.db');sched=ContinuousScheduler(state,None,store,router=MultiProviderRouter(real),governor=ResourceGovernor(hard_worker_cap=3));start=time.perf_counter();sched.start()
    while not state.completed_at and time.perf_counter()-start<600:
        await asyncio.sleep(.25)
    passed=bool(state.completed_at and task.conversation_turns>=2 and task.result and 'CEO_LIVE_VALIDATED' in task.result and state.human_interventions_required==0)
    report={'passed':passed,'provider':task.provider_name,'turns':task.conversation_turns,'interventions_required':state.human_interventions_required,'interventions_avoided':state.human_interventions_avoided,'result_excerpt':(task.result or '')[-1000:]}
    reg=ValidationRegistry(data/'validation_registry.json')
    reg.record('conversation_controller',ValidationEvidence('live-conversation','live','windows-live-provider',passed,json.dumps(report,default=str)))
    reg.record('scheduler',ValidationEvidence('live-scheduler','live','windows-live-provider',passed,json.dumps(report,default=str)))
    if task.provider_name and 'browser' in task.provider_name.lower():
        reg.record('browser_worker',ValidationEvidence('live-browser-chat','live','windows-live-provider',passed,json.dumps(report,default=str)))
    report['release_gates']=StrictReleaseGates().assess(reg)
    out=data/'LIVE_SERVICE_VALIDATION.json';out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(report,indent=2,ensure_ascii=False));print(out)

if __name__=='__main__':asyncio.run(main())
