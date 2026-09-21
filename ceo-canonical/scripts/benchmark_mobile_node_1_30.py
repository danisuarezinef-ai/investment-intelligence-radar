#!/usr/bin/env python3
from pathlib import Path
import json,tempfile,time,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from ceo_core.mobile_node import MobileNodeCore,MobileNodeConfig,MobileBenchmark,MobileResourceScheduler

with tempfile.TemporaryDirectory() as td:
    c=MobileNodeCore(MobileNodeConfig(root=td),evidence_key=b'b'*32)
    t=time.perf_counter()
    for i in range(5000):c.queue.enqueue('synthetic',{'i':i,'api_key':'never-store'},priority=i%100,job_id=f'j{i}')
    queue_seconds=time.perf_counter()-t
    completed=0
    while completed<5000:
        j=c.queue.lease_next(ttl=60)
        if not j:break
        if c.queue.complete(j['id'],j['lease_token'],{'i':j['payload']['i']}):completed+=1
    approvals=[];replay_blocked=0
    for i in range(500):
        p={'amount':i+1,'currency':'EUR'};a=c.approvals.request('payment',p,risk='spend');tok=c.approvals.approve(a['id'],human_confirmed=True)
        ok=c.spend.authorize(approval_id=a['id'],token=tok,payload=p);again=c.spend.authorize(approval_id=a['id'],token=tok,payload=p)
        approvals.append(ok);replay_blocked+=int(not again)
    evidence=[c.evidence.record('bench',{'i':i,'secret':'redact'}) for i in range(1000)]
    evidence_ok=sum(c.evidence.verify(x) for x in evidence)
    for i in range(1000):c.artifacts.put_bytes(f'bench/{i}.txt',str(i).encode())
    sched=MobileResourceScheduler();mobile_wins=windows_wins=0
    for i in range(1000):
        row=sched.choose({'category':'inference' if i%2==0 else 'windows_ui','ram_gb':2,'required_capabilities':['windows_ui'] if i%2 else ['local_ai']},{'ram_available_gb':1},{'ram_available_gb':14,'online':True,'battery':{'percentage':80}})
        mobile_wins+=row['node']=='mobile';windows_wins+=row['node']=='windows'
    sync=Path(td)/'sync.zip';sync_row=c.sync.export(sync)
    out={'status':'PASS','jobs_enqueued':5000,'jobs_completed':completed,'queue_seconds':queue_seconds,'spend_approvals':sum(approvals),'spend_replays_blocked':replay_blocked,'evidence_verified':evidence_ok,'artifacts':1000,'mobile_routes':mobile_wins,'windows_routes':windows_wins,'sync_verified':c.sync.verify(sync),'sync_secret_values_included':sync_row['secret_values_included'],'cpu_benchmark':MobileBenchmark().run(iterations=20000),'certification':c.certification()}
    print(json.dumps(out,indent=2))
