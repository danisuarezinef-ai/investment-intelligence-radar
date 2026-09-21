from __future__ import annotations
import asyncio,json,os,tempfile,time
from pathlib import Path
import psutil
from ceo_core.models import ProjectState,Task,TaskStatus
from ceo_core.simulator import synthetic_project,SyntheticProvider
from ceo_core.scheduler import ContinuousScheduler
from ceo_core.store import CheckpointStore
from ceo_core.resource_governor import ResourceGovernor
from ceo_core.evolution_v07 import StrategicEvolutionLoopV07
from ceo_core.distributed import NodeCapacity,CapacityRegistry,DistributedCoordinator,DistributedLeaseManager,EncryptedNodeEnvelope
from ceo_core.knowledge_graph import GlobalKnowledgeGraph
from ceo_core.prompt_optimization import PromptOptimizationEngine
from ceo_core.endurance import AutonomousEnduranceBenchmark
from ceo_core.conversation_controller import ConversationController
from ceo_core.contracts import WorkerResult

class MemoryStore(CheckpointStore):
    def __init__(self): self.state=None
    def save(self,state): self.state=state
    def load(self): return self.state

class ExactGovernor(ResourceGovernor):
    def __init__(self,n): self.n=n
    def hardware_capacity(self): return self.n
    def target_concurrency(self,power_percent): return self.n
    def adaptive_target(self,power_percent,**kwargs): return self.n
    def snapshot(self): return {'cpu_percent':0,'ram_percent':0,'hardware_worker_capacity':self.n,'logical_cpus':self.n,'ram_total_gb':64,'ram_available_gb':60,'ram_used_gb':4}
    def limits(self,power_percent): return {'total_workers':self.n,'browser_workers':max(1,self.n//4),'api_workers':self.n,'local_workers':self.n,'file_workers':self.n,'ram_soft_percent':90,'cpu_soft_percent':90}

async def stress(workers:int,tasks:int=1000):
    s=synthetic_project(tasks);p=SyntheticProvider(delay=.001)
    sch=ContinuousScheduler(s,p,MemoryStore(),governor=ExactGovernor(workers));start=time.perf_counter();sch.start()
    while not s.completed_at:
        await asyncio.sleep(.005)
        if time.perf_counter()-start>45:raise TimeoutError((workers,tasks))
    return {'workers':workers,'tasks':tasks,'seconds':round(time.perf_counter()-start,4),'calls':p.calls,'failed':sum(t.status==TaskStatus.FAILED for t in s.leaf_tasks)}

async def fault_endurance():
    s=synthetic_project(1000);s.metadata['enable_v07']=True;s.metadata['strategic_tick_interval']=10;s.metadata['max_failure_split_depth']=1
    for i,t in enumerate(s.tasks.values()):
        t.metadata.update({'task_type':'research' if i%2 else 'analysis','uncertainty':.8 if i%7==0 else .3,'impact':.8 if i%11==0 else .4,'expected_novelty':.7})
    p=SyntheticProvider(delay=.0005,fail_every=11,timeout_every=17)
    sch=ContinuousScheduler(s,p,MemoryStore(),governor=ExactGovernor(200));start=time.perf_counter();sch.start()
    while not s.completed_at:
        await asyncio.sleep(.01)
        if time.perf_counter()-start>60:return {'completed':False,'seconds':round(time.perf_counter()-start,3)}
    m=AutonomousEnduranceBenchmark().measure(s)
    return {'completed':True,'seconds':round(time.perf_counter()-start,3),'calls':p.calls,'metrics':m.__dict__ if hasattr(m,'__dict__') else {k:getattr(m,k) for k in m.__slots__},'strategic':s.metadata.get('strategic_loop_v07',{})}

class LongTurnProvider(SyntheticProvider):
    async def execute(self,request):
        self.calls+=1
        if self.calls<61:return WorkerResult(provider=self.name,kind=self.kind,text=f'turn {self.calls} <CEO_RESULT>{{"status":"continue","reason":"more","next_instruction":"continue","followups":[],"requires_user":false}}</CEO_RESULT>',conversation_id='endurance')
        return WorkerResult(provider=self.name,kind=self.kind,text='done <CEO_RESULT>{"status":"complete","reason":"done","followups":[],"requires_user":false}</CEO_RESULT>',conversation_id='endurance')

async def long_conversation():
    s=ProjectState(goal='60-turn autonomy',goal_definition='Complete a long autonomous conversation',completion_criteria=['done'],goal_constraints=['no user prompting']);t=Task(title='Long work',estimated_seconds=.001);s.tasks[t.id]=t;s.root_task_ids=[t.id]
    p=LongTurnProvider();sch=ContinuousScheduler(s,p,MemoryStore(),governor=ExactGovernor(1),controller=ConversationController(max_turns=100));start=time.perf_counter();sch.start()
    while not s.completed_at:
        await asyncio.sleep(.005)
        if time.perf_counter()-start>30:raise TimeoutError('long conversation')
    return {'turns':t.conversation_turns,'avoided':s.human_interventions_avoided,'required':s.human_interventions_required,'seconds':round(time.perf_counter()-start,4)}

def strategic_scale(n:int=10000):
    s=synthetic_project(n);s.goal='Evidence analysis';s.goal_definition='Verify and synthesize evidence';s.completion_criteria=['verified synthesis'];s.goal_constraints=['no fabrication'];s.metadata['enable_v07']=True
    for i,t in enumerate(s.tasks.values()):t.metadata.update({'task_type':'research' if i%3 else 'analysis','uncertainty':(i%10)/10,'impact':.6,'expected_novelty':.5})
    start=time.perf_counter();out=StrategicEvolutionLoopV07().tick(s);elapsed=time.perf_counter()-start
    return {'tasks':n,'seconds':round(elapsed,4),'directors':out['directors'],'knowledge_nodes':out['knowledge_nodes'],'drift_count':out['drift_count']}

def distributed_scale(n:int=5000):
    s=synthetic_project(n);reg=CapacityRegistry()
    nodes=[NodeCapacity('node-a',16,32,8,12,5),NodeCapacity('node-b',8,16,0,8,3),NodeCapacity('node-c',32,64,16,20,8),NodeCapacity('node-d',4,8,0,2,1)]
    for x in nodes:reg.register(s,x)
    start=time.perf_counter();assign=DistributedCoordinator().assign(s,s.leaf_tasks,reg);assign_seconds=time.perf_counter()-start
    # simulate in-flight work on the best node, then lose it and reassign without duplicating completed work
    for tid in assign.get('node-c',[]): s.tasks[tid].status=TaskStatus.RUNNING
    recovered=DistributedCoordinator().recover_node(s,'node-c');start=time.perf_counter();assign2=DistributedCoordinator().assign(s,[s.tasks[x] for x in recovered],reg);recover_seconds=time.perf_counter()-start
    env=EncryptedNodeEnvelope(b'benchmark-node-key-material');token=env.seal({'tasks':list(s.tasks)[:20],'api_key':'must_not_leave_node'});decoded=env.open(token)
    return {'tasks':n,'initial_assignment_seconds':round(assign_seconds,4),'nodes_used':{k:len(v) for k,v in assign.items()},'recovered_from_failed_node':len(recovered),'reassign_seconds':round(recover_seconds,4),'reassigned_nodes':{k:len(v) for k,v in assign2.items()},'encrypted_payload_ok':bool(decoded and 'api_key' not in decoded)}

def knowledge_scale(n:int=10000):
    s=ProjectState(goal='graph');g=GlobalKnowledgeGraph();start=time.perf_counter()
    for i in range(n):
        g.add_node(s,f'n{i}','claim',f'claim {i}')
        if i:g.add_edge(s,f'n{i}',f'n{i-1}','depends_on',.8)
    build=time.perf_counter()-start;start=time.perf_counter();neighbors=g.neighbors(s,f'n{n//2}');query=time.perf_counter()-start
    return {'nodes':n,'edges':n-1,'build_seconds':round(build,4),'neighbor_query_seconds':round(query,6),'neighbors':len(neighbors)}

def prompt_learning():
    s=ProjectState(goal='prompt');p=PromptOptimizationEngine();a=p.register(s,'A','p','research');b=p.register(s,'B','p','research')
    for _ in range(10):p.record(s,a.id,.72,True);p.record(s,b.id,.9,True)
    return {'champion':p.champion(s,'p','research'),'challenger_promoted':p.promote(s,a.id,b.id,min_runs=5,margin=.05),'score_a':round(p.score(s,a.id),3),'score_b':round(p.score(s,b.id),3)}

async def main():
    process=psutil.Process(os.getpid());baseline=process.memory_info().rss
    concurrency=[await stress(w) for w in (10,50,100,500)]
    report={
      'version':'0.7.0rc0',
      'strategic_scale':strategic_scale(),
      'distributed_scale':distributed_scale(),
      'knowledge_scale':knowledge_scale(),
      'prompt_learning':prompt_learning(),
      'concurrency':concurrency,
      'fault_endurance':await fault_endurance(),
      'long_conversation':await long_conversation(),
      'rss_final_delta_mb':round((process.memory_info().rss-baseline)/(1024**2),2),
    }
    Path('reports/MVP_0.7_RC_BENCHMARKS.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
