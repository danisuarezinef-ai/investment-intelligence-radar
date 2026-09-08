"""Orchestrates historical discovery without allowing historical-only promotion."""
import json
from radar_core import con, now
from radar_historical_lab import run_historical_lab
from radar_brain_evolution import Candidate, init_brain_db, record_lineage, record_evidence, promotion_gate


def _latest_run(run_id):
    c=con();r=c.execute('select base_model,candidate_version,folds,positive_folds,mean_gain,test_objective_champion,test_objective_challenger,candidate_weights,metadata from historical_lab_runs where id=?',(run_id,)).fetchone();c.close()
    if not r:return None
    meta=json.loads(r[8] or '{}');return {'base':r[0],'candidate':r[1],'folds':r[2],'positive':r[3],'mean_gain':r[4] or 0,'test_champion':r[5] or 0,'test_challenger':r[6] or 0,'weights':json.loads(r[7] or '{}'),'meta':meta}


def run_brain_discovery():
    """Historical data may discover a shadow champion; it can never replace active model."""
    init_brain_db();lab=run_historical_lab(promote=False)
    if not lab.get('run_id'):return {'lab':lab,'shadow_created':False,'real_trading':False}
    r=_latest_run(lab['run_id']);lineage=f"hist:{r['base']}:run{lab['run_id']}:{lab.get('selected_challenger','candidate')}"
    cand=Candidate(lineage,1,r['weights'],f"champion:{r['base']}")
    status='shadow' if lab.get('accepted') else 'rejected_historical'
    record_lineage(cand,status,'historical evidence only; live gate required',{'lab':lab})
    n=max(1,int(lab.get('observations',1)))
    # Walk-forward evidence, temporal vault and untouched final test are kept separate.
    record_evidence(lineage,'historical_walk_forward','multi','multi',n,float(lab.get('mean_gain') or 0),metadata={'folds':lab.get('folds'),'positive_ratio':lab.get('positive_ratio')})
    record_evidence(lineage,'historical_vault','multi','multi',int(lab.get('vault_n') or 1),float(lab.get('vault_gain') or 0),metadata={'untouched_during_evolution':True})
    record_evidence(lineage,'historical_final_test','multi','multi',int(lab.get('test_n') or 1),float(lab.get('test_gain') or 0),hit_rate=float((lab.get('challenger_test') or {}).get('hit_rate') or 0),metadata={'untouched_until_selection':True})
    gate=promotion_gate(lineage)
    return {'lab':lab,'lineage':lineage,'shadow_created':bool(lab.get('accepted')),'gate':gate,'real_trading':False}
