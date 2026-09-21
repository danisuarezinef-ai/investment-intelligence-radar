from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
import psutil
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ceo_core.validation_harness import (
    destructive_persistence_validation,
    idempotency_validation,
    endurance_validation,
    memory_retention_validation,
)

async def main() -> int:
    outdir=Path(os.getenv('CEO_TEST_OUT') or 'reports/windows-tested').resolve(); outdir.mkdir(parents=True,exist_ok=True)
    ram_gb=psutil.virtual_memory().total/(1024**3)
    # Keep physical-Windows diagnostics bounded on low-memory machines. The purpose here
    # is repeated behavior/recovery evidence, not an artificial maximum-load benchmark.
    if ram_gb < 6:
        destructive_tasks=250; idem_tasks=250; idem_cycles=6; endurance_tasks=300; mem_cycles=4; mem_tasks=750
    elif ram_gb < 12:
        destructive_tasks=400; idem_tasks=400; idem_cycles=8; endurance_tasks=450; mem_cycles=5; mem_tasks=1200
    else:
        destructive_tasks=500; idem_tasks=500; idem_cycles=10; endurance_tasks=600; mem_cycles=6; mem_tasks=2000
    report={'ram_gb':round(ram_gb,2),'profile':{'destructive_tasks':destructive_tasks,'idempotency_tasks':idem_tasks,'idempotency_cycles':idem_cycles,'endurance_tasks':endurance_tasks,'memory_cycles':mem_cycles,'memory_tasks_per_cycle':mem_tasks}}
    report['destructive']=destructive_persistence_validation(task_count=destructive_tasks)
    report['idempotency']=idempotency_validation(task_count=idem_tasks, cycles=idem_cycles)
    report['endurance']=await endurance_validation(tasks=endurance_tasks)
    report['memory']=memory_retention_validation(cycles=mem_cycles, tasks_per_cycle=mem_tasks)
    checks=[report[k] for k in ('destructive','idempotency','endurance','memory')]
    report['passed']=all(x.get('passed', False) for x in checks)
    path=outdir/'WINDOWS_BOUNDED_DIAGNOSTICS.json'; path.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    print(json.dumps(report,indent=2,default=str))
    print(path)
    return 0 if report['passed'] else 1

if __name__=='__main__': raise SystemExit(asyncio.run(main()))
