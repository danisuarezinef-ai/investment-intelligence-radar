#!/usr/bin/env python3
from pathlib import Path
import json,time,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ceo_core.mobile_node import MobileNodeCore,MobileNodeConfig
core=MobileNodeCore(MobileNodeConfig())
print('CEO Mobile durable worker loop started. Ctrl+C to stop.')
while True:
    if core.emergency_active():time.sleep(2);continue
    job=core.queue.lease_next(ttl=300)
    if not job:time.sleep(1);continue
    try:
        kind=job['kind'];payload=job['payload']
        if kind=='local_ai':res=core.worker.execute(str(payload.get('instruction','')),payload.get('context',{}))
        elif kind=='hash_file':
            p=Path(payload['path']).expanduser().resolve();res={'path':str(p),'sha256':__import__('hashlib').sha256(p.read_bytes()).hexdigest()}
        elif kind=='benchmark':res=__import__('ceo_core.mobile_node',fromlist=['MobileBenchmark']).MobileBenchmark().run(iterations=int(payload.get('iterations',100000)))
        else:res={'echo':payload,'kind':kind}
        core.queue.complete(job['id'],job['lease_token'],res)
    except Exception as exc:core.queue.fail(job['id'],job['lease_token'],f'{type(exc).__name__}: {exc}',retry=False)
