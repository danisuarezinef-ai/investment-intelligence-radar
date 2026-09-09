"""Read-only brain/simulator dashboard contract."""
from __future__ import annotations
from radar_experiment_memory_v2 import memory_snapshot
from radar_autonomous_simulator_v1 import simulator_status
from radar_autonomy_e2e_v1 import e2e_cycle_status,soak_status
REAL_TRADING=False


def brain_dashboard(*,forward_status=None,paper_status=None,champion=None,learning_status=None,cloud_status=None):
    mem=memory_snapshot(50);experiments=mem.get('experiments') or []
    active=[x for x in experiments if x.get('stage') in ('SIMULATED','SHADOW_REVIEW','SHADOW')]
    grave=[x for x in experiments if x.get('stage')=='GRAVEYARD']
    shadow=[x for x in experiments if x.get('stage') in ('SHADOW_REVIEW','SHADOW')]
    try:sim=simulator_status()
    except Exception as exc:sim={'active':False,'status':'ERROR','error':str(exc)[:300],'real_trading':False}
    try:e2e=e2e_cycle_status();soak=soak_status()
    except Exception as exc:e2e={'status':'ERROR','error':str(exc)[:300]};soak={'status':'ERROR','error':str(exc)[:300]}
    return {'brain_state':'RESEARCHING_CONTINUOUSLY','research_protocol':'STRICT_CHRONOLOGICAL_V4','experiments_total':len(experiments),'experiments_active':active[:10],'experiments_graveyard_count':len(grave),'shadow_candidates':shadow[:10],'simulator':sim,'e2e':e2e,'unattended_soak':soak,'forward':forward_status or {'status':'NOT_VERIFIED'},'paper':paper_status or {'status':'NOT_VERIFIED'},'champion':champion or {'status':'NOT_VERIFIED'},'learning':learning_status or {'status':'NOT_VERIFIED'},'cloud':cloud_status or {'status':'NOT_VERIFIED'},'automatic_experiment_generation':True,'automatic_live_promotion':False,'real_trading':False}
