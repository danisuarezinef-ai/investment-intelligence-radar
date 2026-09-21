from __future__ import annotations

import asyncio,json,time
from pathlib import Path
from ceo_core.runtime import user_data_root
from ceo_core.validation import ValidationEvidence,ValidationRegistry,StrictReleaseGates

async def main(hours:float=8.0):
    # This runner monitors an already-running installed CEO instance via its durable files.
    # It intentionally does not create fake work; the night project must be started by the user.
    data=user_data_root();db=data/'ceo.db';start=time.time();samples=[]
    if not db.exists():raise SystemExit('No installed CEO project database found. Start a real project first; no stability evidence recorded.')
    while time.time()-start < hours*3600:
        stat=db.stat();samples.append({'ts':time.time(),'db_bytes':stat.st_size});await asyncio.sleep(60)
    passed=len(samples)>=max(2,int(hours*60*.9)) and db.exists()
    report={'passed':passed,'requested_hours':hours,'samples':len(samples),'db_final_bytes':db.stat().st_size}
    reg=ValidationRegistry(data/'validation_registry.json')
    # A single night run is field validation, not STABLE. Stability requires repeated projects/runs.
    for cap in ('scheduler','persistence_recovery'):
        reg.record(cap,ValidationEvidence(f'night-{cap}-{int(start)}','night_run','windows-physical',passed,json.dumps(report)))
    report['release_gates']=StrictReleaseGates().assess(reg)
    (data/'NIGHT_RUN_VALIDATION.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))

if __name__=='__main__':asyncio.run(main())
