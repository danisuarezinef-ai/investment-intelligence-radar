"""Read-only brain/simulator dashboard contract."""
from __future__ import annotations
from radar_experiment_memory_v2 import memory_snapshot
from radar_simulation_v2 import simulation_summary
REAL_TRADING=False


def brain_dashboard(*,forward_status=None,paper_status=None,champion=None,learning_status=None,cloud_status=None):
    mem=memory_snapshot(50);experiments=mem.get('experiments') or []
    active=[x for x in experiments if x.get('stage') in ('SIMULATED','SHADOW_REVIEW','SHADOW')]
    grave=[x for x in experiments if x.get('stage')=='GRAVEYARD']
    shadow=[x for x in experiments if x.get('stage') in ('SHADOW_REVIEW','SHADOW')]
    try:sim=simulation_summary('forward-live')
    except Exception as exc:sim={'configured':False,'error':str(exc)[:300],'real_trading':False}
    return {'brain_state':'RESEARCHING_CONTINUOUSLY','experiments_total':len(experiments),'experiments_active':active[:10],'experiments_graveyard_count':len(grave),'shadow_candidates':shadow[:10],'simulator':sim,'forward':forward_status or {'status':'NOT_VERIFIED'},'paper':paper_status or {'status':'NOT_VERIFIED'},'champion':champion or {'status':'NOT_VERIFIED'},'learning':learning_status or {'status':'NOT_VERIFIED'},'cloud':cloud_status or {'status':'NOT_VERIFIED'},'automatic_experiment_generation':True,'automatic_live_promotion':False,'real_trading':False}
