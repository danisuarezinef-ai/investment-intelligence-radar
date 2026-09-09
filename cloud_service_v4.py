"""Production entrypoint v4: existing cloud service plus prospective closed-loop PAPER runtime."""
import json,threading,time
import cloud_service as base
from radar_core import now
from radar_forward_engine import mature_forward_outcomes
from radar_forward_outcome_sync_v1 import sync_forward_outcomes_once
from radar_closed_loop_runtime_v1 import closed_loop_cycle

REAL_TRADING=False


def closed_loop_runtime_loop():
    print('[closed-loop] prospective PAPER runtime enabled; REAL_TRADING OFF',flush=True)
    # Market collection runs every 5 minutes. Evaluate shortly after each possible fresh mark.
    time.sleep(20)
    while True:
        try:
            matured=mature_forward_outcomes()
            synced=sync_forward_outcomes_once()
            cycle=closed_loop_cycle('1d')
            base.write_status(closed_loop='OK',closed_loop_at=now(),closed_loop_status=cycle.get('status'),
                              closed_loop_forward=cycle.get('forward_records',0),closed_loop_matured=matured,
                              closed_loop_sync={k:v for k,v in synced.items() if k!='remote'},
                              real_trading=False)
            print('[closed-loop] '+json.dumps({'matured':matured,'sync':{k:v for k,v in synced.items() if k!='remote'},
                  'status':cycle.get('status'),'forward_records':cycle.get('forward_records'),
                  'optimizer':(cycle.get('optimizer') or {}).get('status'),
                  'competition':(cycle.get('champion_challenger') or {}).get('status'),
                  'execution':(cycle.get('execution') or {}).get('status'),'real_trading':False},ensure_ascii=False)[:2600],flush=True)
        except Exception as exc:
            print('[closed-loop] ERROR '+repr(exc),flush=True)
            base.write_status(closed_loop='ERROR',closed_loop_error=str(exc)[:700],real_trading=False)
        time.sleep(300)


if __name__=='__main__':
    threading.Thread(target=base.supabase_sync_loop,name='supabase-sync',daemon=True).start()
    threading.Thread(target=base.learning_sync_loop,name='learning-sync',daemon=True).start()
    threading.Thread(target=base.learning_loop,name='learning-engine',daemon=True).start()
    threading.Thread(target=closed_loop_runtime_loop,name='closed-loop-paper',daemon=True).start()
    base.run_worker.main()
