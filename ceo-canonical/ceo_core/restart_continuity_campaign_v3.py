from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from .models import ProjectState,Task,TaskStatus
from .store import JsonCheckpointStore
@dataclass(slots=True)
class RestartCampaignResult:
    restarts:int; tasks_preserved:int; running_requeued:int; duplicate_ids:int; violations:int
    def to_dict(self):return asdict(self)
class RestartContinuityCampaignV3:
    def run(self,*,restarts:int=20)->RestartCampaignResult:
        with TemporaryDirectory(prefix='dev226-') as td:
            s=ProjectState(goal='restart campaign')
            for i in range(12):
                t=Task(title=f't{i}',status=TaskStatus.RUNNING if i%4==0 else TaskStatus.READY,metadata={'task_role':'productive'})
                s.tasks[t.id]=t;s.root_task_ids.append(t.id)
            store=JsonCheckpointStore(Path(td)/'state.json');store.save(s)
            requeued=0;viol=0
            for _ in range(restarts):
                x=store.load();
                if x is None: viol+=1;break
                before=sum(t.status==TaskStatus.RUNNING for t in x.tasks.values())
                x=store.prepare_for_resume(x)
                after=sum(t.status in {TaskStatus.READY,TaskStatus.RETRY} for t in x.tasks.values())
                requeued+=max(0,min(before,after));store.save(x)
            final=store.load(); ids=list(final.tasks) if final else []
            return RestartCampaignResult(restarts,len(ids),requeued,len(ids)-len(set(ids)),viol+int(len(ids)!=12))
