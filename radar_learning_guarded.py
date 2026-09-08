import json, math, statistics
from datetime import datetime, timezone

from radar_core import con, now
from radar_learning import init_learning_db, active_model, capture_predictions, evaluate_predictions, detect_regime, weak_signal_scan, build_portfolio

MIN_OBSERVATIONS=40
VALIDATION_FRACTION=0.30
MAX_WEIGHT_STEP=0.02
MAX_TOTAL_STEP=0.08
MIN_OBJECTIVE_GAIN=0.01


def init_guarded_learning_db():
    init_learning_db();c=con();c.execute('''create table if not exists model_evaluations(
      id integer primary key, created_at text not null, model_version text not null,
      evaluation_role text not null, sample_start text, sample_end text,
      observations integer not null, hit_rate real, brier real,
      signed_return real, objective real, metadata text)''');c.commit();c.close()


def _rows():
    init_guarded_learning_db();c=con();rows=c.execute('''select p.created_at,p.features,o.return_pct,p.confidence,o.hit
      from prediction_outcomes o join predictions p on p.id=o.prediction_id
      where o.return_pct is not null order by p.created_at,p.id''').fetchall();c.close();out=[]
    for ts,fjson,ret,conf,hit in rows:
        try:f=json.loads(fjson or '{}')
        except Exception:f={}
        out.append({'ts':ts,'features':f,'return_pct':float(ret or 0),'stored_confidence':float(conf or .5),'stored_hit':int(hit or 0)})
    return out


def _score(weights,features):
    return sum(float(weights.get(k,0))*float(features.get(k,0) or 0) for k in weights)


def _confidence(z):
    return max(.05,min(.95,.50+.40*math.tanh(abs(float(z))*2.0)))


def evaluate_weights(weights,rows):
    if not rows:return {'n':0,'hit_rate':0.0,'brier':1.0,'signed_return':0.0,'objective':-1.0}
    hits=[];briers=[];signed=[]
    for r in rows:
        z=_score(weights,r['features']);direction=1.0 if z>=0 else -1.0;ret=r['return_pct'];hit=1 if direction*ret>0 else 0;conf=_confidence(z)
        hits.append(hit);briers.append((conf-hit)**2);signed.append(direction*ret)
    hit_rate=statistics.mean(hits);brier=statistics.mean(briers);signed_return=statistics.mean(signed)
    # Direction dominates. Return contribution is clipped so outliers cannot hijack learning.
    ret_term=max(-1.0,min(1.0,signed_return/5.0))
    objective=hit_rate + 0.12*ret_term - 0.20*brier
    return {'n':len(rows),'hit_rate':hit_rate,'brier':brier,'signed_return':signed_return,'objective':objective}


def _candidate_weights(current,train):
    deltas={k:0.0 for k in current}
    if not train:return dict(current),deltas
    for k in current:
        xs=[]
        for r in train:
            x=float(r['features'].get(k,0) or 0);y=max(-1.0,min(1.0,r['return_pct']/5.0));xs.append(x*y)
        signal=statistics.mean(xs) if xs else 0.0
        deltas[k]=max(-MAX_WEIGHT_STEP,min(MAX_WEIGHT_STEP,0.06*signal))
    total=sum(abs(v) for v in deltas.values())
    if total>MAX_TOTAL_STEP and total>0:
        scale=MAX_TOTAL_STEP/total;deltas={k:v*scale for k,v in deltas.items()}
    proposed={k:max(-0.50,min(0.50,float(current.get(k,0))+deltas[k])) for k in current}
    return proposed,deltas


def _record_eval(version,role,rows,metrics,metadata=None):
    c=con();c.execute('''insert into model_evaluations(created_at,model_version,evaluation_role,sample_start,sample_end,observations,hit_rate,brier,signed_return,objective,metadata)
      values(?,?,?,?,?,?,?,?,?,?,?)''',(now(),version,role,rows[0]['ts'] if rows else None,rows[-1]['ts'] if rows else None,metrics['n'],metrics['hit_rate'],metrics['brier'],metrics['signed_return'],metrics['objective'],json.dumps(metadata or {})));c.commit();c.close()


def guarded_learn(min_observations=MIN_OBSERVATIONS):
    rows=_rows();model=active_model();current=dict(model['weights'])
    if len(rows)<min_observations:
        return {'accepted':False,'reason':'insufficient_observations','n':len(rows),'required':min_observations,'version':model['version']}
    cut=max(1,int(len(rows)*(1.0-VALIDATION_FRACTION)));train=rows[:cut];valid=rows[cut:]
    if len(valid)<12:return {'accepted':False,'reason':'insufficient_validation','n':len(rows),'validation_n':len(valid)}
    proposed,deltas=_candidate_weights(current,train)
    before=evaluate_weights(current,valid);after=evaluate_weights(proposed,valid)
    train_before=evaluate_weights(current,train);train_after=evaluate_weights(proposed,train)
    _record_eval(model['version'],'champion_holdout',valid,before,{'weights':current})
    _record_eval(model['version']+'-challenger','challenger_holdout',valid,after,{'weights':proposed,'deltas':deltas})
    gain=after['objective']-before['objective']
    qualified=(gain>=MIN_OBJECTIVE_GAIN and after['hit_rate']>=before['hit_rate'] and train_after['objective']>=train_before['objective']-0.01 and sum(abs(v) for v in deltas.values())<=MAX_TOTAL_STEP+1e-9)
    accepted=False
    new_version=model['version']
    if qualified:
        parts=model['version'].split('.')
        try:new_version=f"{parts[0]}.{parts[1]}.{int(parts[2])+1}"
        except Exception:new_version=model['version']+'-next'
        c=con();c.execute('''insert or ignore into model_versions(version,created_at,parent_version,status,weights,metrics,notes)
          values(?,?,?,?,?,?,?)''',(new_version,now(),model['version'],'shadow',json.dumps(proposed),json.dumps({'validation':after,'training':train_after,'gain':gain}),'Shadow candidate only; operational promotion requires Brain live gate'));c.commit();c.close()
    c=con();c.execute('''insert into learning_cycles(created_at,prior_version,new_version,observations,objective_before,objective_after,accepted,weight_delta,calibration,notes)
      values(?,?,?,?,?,?,?,?,?,?)''',(now(),model['version'],new_version,len(rows),before['objective'],after['objective'],1 if accepted else 0,json.dumps(deltas),json.dumps({'validation_before':before,'validation_after':after}),'Chronological holdout; bounded step; no real trading'));c.commit();c.close()
    return {'accepted':accepted,'shadow_qualified':qualified,'n':len(rows),'train_n':len(train),'validation_n':len(valid),'prior_version':model['version'],'new_version':new_version,'objective_before':before['objective'],'objective_after':after['objective'],'gain':gain,'validation_before':before,'validation_after':after,'deltas':deltas}


def run_guarded_cycle(force_predictions=False):
    init_guarded_learning_db();regime=detect_regime(True);created=capture_predictions(force_predictions);evaluated=evaluate_predictions();weak=weak_signal_scan();portfolio=build_portfolio('1m');learning=guarded_learn();return {'regime':regime,'predictions_created':created,'outcomes_evaluated':evaluated,'weak_signals_created':weak,'portfolio_positions':len(portfolio),'learning':learning,'trading_real':False}


def learning_health():
    init_guarded_learning_db();m=active_model();c=con();last=c.execute('select created_at,prior_version,new_version,observations,objective_before,objective_after,accepted from learning_cycles order by id desc limit 1').fetchone();evals=c.execute('select model_version,evaluation_role,observations,hit_rate,brier,signed_return,objective,created_at from model_evaluations order by id desc limit 8').fetchall();c.close();return {'active_model':m,'last_cycle':({'ts':last[0],'prior':last[1],'new':last[2],'n':last[3],'before':last[4],'after':last[5],'accepted':bool(last[6])} if last else None),'evaluations':[{'version':r[0],'role':r[1],'n':r[2],'hit_rate':r[3],'brier':r[4],'signed_return':r[5],'objective':r[6],'ts':r[7]} for r in evals],'guardrails':{'min_observations':MIN_OBSERVATIONS,'validation_fraction':VALIDATION_FRACTION,'max_weight_step':MAX_WEIGHT_STEP,'max_total_step':MAX_TOTAL_STEP,'min_objective_gain':MIN_OBJECTIVE_GAIN,'real_trading':False}}
