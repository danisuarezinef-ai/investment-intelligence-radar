"""Auditable Brain Evolution v3 governance. Simulation only."""
from __future__ import annotations
import json, math, random, uuid
from dataclasses import dataclass, field
from typing import Dict, Iterable, List
from radar_core import con, init_db, now

REAL_TRADING=False
EPISTEMIC_WEIGHTS={"historical_train":.15,"historical_walk_forward":.30,"historical_vault":.45,"historical_final_test":.60,"live_forward":1.0}
STATUSES=("candidate","historical_survivor","vault_survivor","historical_finalist","shadow_champion","live_validated","operational_champion","rejected")
FAMILIES=("balanced","fast","slow","low_vol","trend","regime_specialist","causal_specialist","momentum_specialist","mean_reversion","risk_specialist","horizon_specialist","generalist")
VAULTS=(("dotcom_aftermath","2000-03-01","2003-03-31"),("gfc","2007-07-01","2009-06-30"),("euro_crisis","2010-04-01","2012-09-30"),("china_commodity_shock","2014-06-01","2016-03-31"),("volmageddon_trade_war","2018-01-01","2019-12-31"),("covid_crash_rebound","2020-02-01","2021-06-30"),("inflation_hiking_cycle","2021-07-01","2023-10-31"),("ai_capex_cycle","2023-11-01",None))
MAX_GENERATIONS,POPULATION,ELITE=8,18,4
MUTATION_SIGMA,MAX_GENE_STEP,MAX_TOTAL_DISTANCE=.025,.06,.28

@dataclass
class Candidate:
    lineage_id:str; generation:int; weights:Dict[str,float]; parent:str|None=None
    family:str="balanced"; mutation:dict=field(default_factory=dict); specialization:dict=field(default_factory=dict)
    training_method:str="balanced_mutation"; features:List[str]=field(default_factory=list)
    @property
    def lineage(self): return self.lineage_id
    @property
    def specialist_regime(self): return self.specialization.get("regime")

def _cols(c,t): return {r[1] for r in c.execute("pragma table_info("+t+")")}
def _add(c,t,columns):
    old=_cols(c,t)
    for name,kind in columns.items():
        if name not in old:c.execute(f"alter table {t} add column {name} {kind}")

def init_brain_db():
    init_db();c=con()
    c.execute("create table if not exists brain_lineages(id integer primary key,created_at text,lineage text unique,parent text,generation integer,specialist_regime text,weights text,status text,reason text,metrics text)")
    _add(c,"brain_lineages",{"family":"text","mutation":"text","specialization":"text","training_method":"text","features":"text","updated_at":"text"})
    c.execute("create table if not exists brain_evidence(id integer primary key,created_at text,lineage text,tier text,regime text,horizon text,n integer,objective real,hit_rate real,drawdown real,score real,metadata text,evidence_key text unique)")
    c.execute("create table if not exists brain_transfer(id integer primary key,created_at text,lineage text,historical_score real,live_score real,transfer_ratio real,n_live integer,regime text,horizon text,metadata text,unique(lineage,regime,horizon))")
    c.execute("create table if not exists brain_meta_methods(id integer primary key,method text unique,trials integer default 0,historical_wins integer default 0,live_wins integer default 0,transfer_mean real default 0,last_seen text,metadata text)")
    c.execute("create table if not exists brain_vault_registry(id integer primary key,vault_key text unique,start_date text,end_date text,vault_type text default 'rotating',status text default 'sealed',opens integer default 0,last_opened text,candidate_evaluated text,result text,reuse_penalty real default 0,metadata text)")
    c.execute("create table if not exists brain_vault_events(id integer primary key,created_at text,vault_key text,lineage text,action text,purpose text,result text,epistemic_penalty real default 0)")
    c.execute("create table if not exists brain_hall_of_fame(id integer primary key,created_at text,lineage text,category text,reason text,score real,metadata text,unique(lineage,category))")
    c.execute("create table if not exists brain_graveyard(id integer primary key,created_at text,lineage text unique,reason text,failed_regime text,failed_horizon text,score real,metadata text)")
    c.execute("create table if not exists brain_shadow_predictions(id integer primary key,prediction_key text unique,created_at text,lineage text,symbol text,horizon text,cutoff text,due_at text,score real,confidence real,features text,provenance text,outcome real,evaluated_at text)")
    c.execute("create table if not exists brain_generation_runs(id integer primary key,created_at text,generation integer,champion text,candidates_tested integer,candidates_surviving integer,status text,configuration text,result text)")
    for key,start,end in VAULTS:c.execute("insert into brain_vault_registry(vault_key,start_date,end_date,vault_type,status,metadata) values(?,?,?,'rotating','sealed','{}') on conflict(vault_key) do nothing",(key,start,end))
    c.execute("insert into brain_vault_registry(vault_key,vault_type,status,metadata) values('deep_final_test','deep','sealed','{}') on conflict(vault_key) do nothing")
    c.execute("create index if not exists idx_brain_evidence_lineage on brain_evidence(lineage,tier,horizon)");c.execute("create index if not exists idx_shadow_due on brain_shadow_predictions(evaluated_at,due_at)");c.commit();c.close()

def epistemic_score(evidence:Iterable[dict]):
    num=den=0.
    for e in evidence:
        if e.get('tier') not in EPISTEMIC_WEIGHTS or int(e.get('n') or 0)<=0:continue
        w=EPISTEMIC_WEIGHTS[e['tier']]*math.sqrt(int(e['n']));num+=w*(float(e.get('objective') or 0)-.15*abs(float(e.get('drawdown') or 0)));den+=w
    return num/den if den else None

def anti_overfit_score(fold_scores,complexity,regime_scores,*,asset_shares=None,horizon_scores=None,turnover=0,perturbation_drop=0,vault_drop=0,trade_concentration=0):
    if not fold_scores:return None
    mean=sum(fold_scores)/len(fold_scores);disp=math.sqrt(sum((x-mean)**2 for x in fold_scores)/len(fold_scores))
    spread=lambda xs:max(xs)-min(xs) if len(xs)>1 else 0
    p={"fold_dispersion":.35*disp,"regime_dependency":.10*spread(list(regime_scores.values())),"asset_dependency":.10*max((asset_shares or {}).values(),default=0),"complexity":.002*max(0,complexity-5),"period_sensitivity":.10*max(0,perturbation_drop),"turnover":.02*max(0,turnover),"trade_concentration":.10*max(0,trade_concentration),"horizon_dependency":.08*spread(list((horizon_scores or {}).values())),"vault_deterioration":.20*max(0,vault_drop)}
    return {"score":mean-sum(p.values()),"mean":mean,"penalties":p}

def mutate(parent,keys,rng,regime=None,family=None):
    w=dict(parent.weights);d={}
    for k in keys:
        if rng.random()<.45:
            delta=max(-MAX_GENE_STEP,min(MAX_GENE_STEP,rng.gauss(0,MUTATION_SIGMA)));w[k]=max(-.5,min(.5,w.get(k,0)+delta));d[k]=w[k]-parent.weights.get(k,0)
    dist=sum(abs(w[k]-parent.weights.get(k,0)) for k in keys)
    if dist>MAX_TOTAL_DISTANCE:
        scale=MAX_TOTAL_DISTANCE/dist;w={k:parent.weights.get(k,0)+(w[k]-parent.weights.get(k,0))*scale for k in keys};d={k:w[k]-parent.weights.get(k,0) for k in keys if w[k]!=parent.weights.get(k,0)}
    fam=family or parent.family;return Candidate(f"{parent.lineage_id}.g{parent.generation+1}.{rng.randrange(10**7):07d}",parent.generation+1,w,parent.lineage_id,fam,{"weight_deltas":d},{"regime":regime} if regime else {},fam,list(keys))

def seed_population(champion_version,weights,regimes=None,seed=42):
    rng=random.Random(seed);base=Candidate(f"champion:{champion_version}",0,dict(weights),family="generalist",features=list(weights));out=[base];regimes=regimes or []
    while len(out)<POPULATION:
        fam=FAMILIES[(len(out)-1)%len(FAMILIES)];reg=regimes[(len(out)-1)%len(regimes)] if regimes and fam=="regime_specialist" else None;out.append(mutate(base,list(weights),rng,reg,fam))
    return out

def select_diverse(scored,elite=ELITE):
    chosen=[]
    for cand,_ in sorted(scored,key=lambda x:x[1],reverse=True):
        distance=min((sum(abs(cand.weights.get(k,0)-x.weights.get(k,0)) for k in set(cand.weights)|set(x.weights)) for x in chosen),default=1)
        if not chosen or distance>=.035 or cand.family not in {x.family for x in chosen}:chosen.append(cand)
        if len(chosen)>=elite:break
    return chosen

def record_lineage(candidate,status='candidate',reason='',metrics=None):
    if status not in STATUSES:raise ValueError('invalid lineage status')
    init_brain_db();c=con();stamp=now();c.execute("""insert into brain_lineages(created_at,lineage,parent,generation,specialist_regime,weights,status,reason,metrics,family,mutation,specialization,training_method,features,updated_at) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) on conflict(lineage) do update set status=excluded.status,reason=excluded.reason,metrics=excluded.metrics,updated_at=excluded.updated_at""",(stamp,candidate.lineage_id,candidate.parent,candidate.generation,candidate.specialist_regime,json.dumps(candidate.weights),status,reason,json.dumps(metrics or {}),candidate.family,json.dumps(candidate.mutation),json.dumps(candidate.specialization),candidate.training_method,json.dumps(candidate.features),stamp));c.commit();c.close()

def record_evidence(lineage,tier,regime,horizon,n,objective,hit_rate=0,drawdown=0,metadata=None,evidence_key=None):
    if tier not in EPISTEMIC_WEIGHTS:raise ValueError('invalid evidence tier')
    if n<0:raise ValueError('n cannot be negative')
    key=evidence_key or str(uuid.uuid4());score=epistemic_score([{"tier":tier,"n":n,"objective":objective,"drawdown":drawdown}]);init_brain_db();c=con();c.execute("insert into brain_evidence(created_at,lineage,tier,regime,horizon,n,objective,hit_rate,drawdown,score,metadata,evidence_key) values(?,?,?,?,?,?,?,?,?,?,?,?) on conflict(evidence_key) do nothing",(now(),lineage,tier,regime,horizon,n,objective,hit_rate,drawdown,score,json.dumps(metadata or {}),key));c.commit();c.close();return score

def transfer_score(historical,live,n_live):
    if n_live<=0 or historical is None or live is None:return None
    return max(-1,min(1,(1-min(2,abs(live-historical)/(abs(historical)+.05)))*min(1,math.log1p(n_live)/math.log(101))))

def promotion_gate(lineage,min_live=40):
    init_brain_db();c=con();rows=c.execute('select tier,n,objective,drawdown from brain_evidence where lineage=?',(lineage,)).fetchall();c.close();ev=[dict(tier=r[0],n=r[1],objective=r[2],drawdown=r[3]) for r in rows];live=[x for x in ev if x['tier']=='live_forward'];hist=[x for x in ev if x['tier']!='live_forward'];hs,ls=epistemic_score(hist),epistemic_score(live);nl=sum(x['n'] for x in live);req={"walk_forward":any(x['tier']=='historical_walk_forward' for x in hist),"vault":any(x['tier']=='historical_vault' for x in hist),"final_test":any(x['tier']=='historical_final_test' for x in hist),"live":nl>=min_live and ls is not None and ls>0};return {"lineage":lineage,"historical_score":hs,"live_score":ls,"transfer_score":transfer_score(hs,ls,nl),"n_live":nl,"shadow_eligible":all(req[k] for k in ('walk_forward','vault','final_test')),"promotion_eligible":all(req.values()),"requirements":req,"real_trading":False}

def freeze_shadow_prediction(lineage,symbol,horizon,cutoff,due_at,score,confidence,features,provenance,prediction_key=None):
    if provenance.get('lookahead') is not False:raise ValueError('lookahead must be explicitly false')
    key=prediction_key or f'{lineage}|{symbol}|{horizon}|{cutoff}';init_brain_db();c=con();c.execute("insert into brain_shadow_predictions(prediction_key,created_at,lineage,symbol,horizon,cutoff,due_at,score,confidence,features,provenance) values(?,?,?,?,?,?,?,?,?,?,?) on conflict(prediction_key) do nothing",(key,now(),lineage,symbol,horizon,cutoff,due_at,score,confidence,json.dumps(features),json.dumps(provenance)));c.commit();c.close();return key

def evaluate_shadow_prediction(key,outcome,evaluated_at=None):
    init_brain_db();c=con();row=c.execute('select outcome from brain_shadow_predictions where prediction_key=?',(key,)).fetchone()
    if not row:c.close();raise KeyError(key)
    if row[0] is not None:c.close();raise ValueError('live prediction outcome is immutable')
    c.execute('update brain_shadow_predictions set outcome=?,evaluated_at=? where prediction_key=? and outcome is null',(float(outcome),evaluated_at or now(),key));c.commit();c.close()

def ensemble_consensus(votes,abstain_threshold=.35):
    if not votes:return {"score":None,"disagreement":None,"confidence":0,"abstain":True,"independent_families":0}
    groups={}
    for v in votes:groups.setdefault(v.get('family') or v.get('lineage'),[]).append(v)
    vals=[sum(float(x['score'])*float(x.get('quality',1)) for x in xs)/max(1e-12,sum(float(x.get('quality',1)) for x in xs)) for xs in groups.values()];mean=sum(vals)/len(vals);dis=math.sqrt(sum((x-mean)**2 for x in vals)/len(vals));conf=max(0,min(1,1-dis));return {"score":mean,"disagreement":dis,"confidence":conf,"abstain":conf<abstain_threshold or dis>.75,"independent_families":len(vals)}

def open_vault(vault_key,lineage,purpose,qualified=False):
    init_brain_db();c=con();row=c.execute('select vault_type,opens from brain_vault_registry where vault_key=?',(vault_key,)).fetchone()
    if not row:c.close();raise KeyError(vault_key)
    if purpose in ('training','candidate_selection'):c.close();raise ValueError('vaults cannot train or select candidates')
    if row[0]=='deep' and not qualified:c.close();raise PermissionError('deep vault requires qualified finalist')
    opens=int(row[1] or 0)+1;penalty=max(0,(opens-1)*.10);stamp=now();c.execute("update brain_vault_registry set status='opened',opens=?,last_opened=?,candidate_evaluated=?,reuse_penalty=? where vault_key=?",(opens,stamp,lineage,penalty,vault_key));c.execute('insert into brain_vault_events(created_at,vault_key,lineage,action,purpose,epistemic_penalty) values(?,?,?,?,?,?)',(stamp,vault_key,lineage,'open',purpose,penalty));c.commit();c.close();return {"vault_key":vault_key,"opens":opens,"reuse_penalty":penalty}

def brain_dashboard(limit=100):
    init_brain_db();c=con();keys=('lineage','parent','generation','family','regime','status','reason','metrics');ls=[dict(zip(keys,r)) for r in c.execute('select lineage,parent,generation,family,specialist_regime,status,reason,metrics from brain_lineages order by id desc limit ?',(limit,))];vkeys=('key','start','end','type','status','opens','last_opened','candidate','reuse_penalty');vs=[dict(zip(vkeys,r)) for r in c.execute('select vault_key,start_date,end_date,vault_type,status,opens,last_opened,candidate_evaluated,reuse_penalty from brain_vault_registry order by id')];active=[x for x in ls if x['status']=='operational_champion'];transfer=[dict(zip(('lineage','historical_score','live_score','transfer_score','n_live','regime','horizon'),r)) for r in c.execute('select lineage,historical_score,live_score,transfer_ratio,n_live,regime,horizon from brain_transfer order by id desc limit ?',(limit,))];meta=[dict(zip(('method','trials','historical_wins','live_wins','transfer_mean','last_seen'),r)) for r in c.execute('select method,trials,historical_wins,live_wins,transfer_mean,last_seen from brain_meta_methods order by trials desc,method')];hall=c.execute('select count(*) from brain_hall_of_fame').fetchone()[0];grave=c.execute('select count(*) from brain_graveyard').fetchone()[0];shadows=c.execute('select count(distinct lineage) from brain_shadow_predictions where evaluated_at is null').fetchone()[0];c.close();cons=ensemble_consensus([]);return {"active_champion":active[0] if len(active)==1 else None,"active_champion_count":len(active),"shadow_champions":shadows,"current_generation":max((x['generation'] for x in ls),default=None),"challengers_tested":len(ls),"challengers_surviving":sum(x['status'] not in ('candidate','rejected') for x in ls),"hall_of_fame":hall,"graveyard":grave,"vaults":vs,"deep_vault":next((x for x in vs if x['type']=='deep'),None),"transfer":transfer,"meta_learning_methods":meta,"model_disagreement":cons['disagreement'],"ensemble_confidence":cons['confidence'],"abstain":cons['abstain'],"epistemic_weights":EPISTEMIC_WEIGHTS,"real_trading":False}
