"""Brain Evolution v2: auditable evolutionary/meta-learning layer.

No real trading. Historical evidence accelerates hypothesis discovery; live forward
outcomes remain the highest epistemic tier. Vault/test outcomes never train candidates.
"""
from __future__ import annotations
import json, math, random, sqlite3
from dataclasses import dataclass
from typing import Dict, Iterable, List
from radar_core import con, now

EPISTEMIC_WEIGHTS={"historical_train":0.15,"historical_walk_forward":0.30,"historical_vault":0.45,"historical_final_test":0.60,"live_forward":1.00}
MAX_GENERATIONS=8
POPULATION=18
ELITE=4
MUTATION_SIGMA=.025
MAX_GENE_STEP=.06
MAX_TOTAL_DISTANCE=.28

@dataclass
class Candidate:
    lineage:str
    generation:int
    weights:Dict[str,float]
    parent:str|None=None
    specialist_regime:str|None=None


def init_brain_db():
    c=con()
    c.execute('''create table if not exists brain_lineages(id integer primary key,created_at text,lineage text unique,parent text,generation integer,specialist_regime text,weights text,status text,reason text,metrics text)''')
    c.execute('''create table if not exists brain_evidence(id integer primary key,created_at text,lineage text,tier text,regime text,horizon text,n integer,objective real,hit_rate real,drawdown real,score real,metadata text)''')
    c.execute('''create table if not exists brain_transfer(id integer primary key,created_at text,lineage text,historical_score real,live_score real,transfer_ratio real,n_live integer,metadata text)''')
    c.execute('''create table if not exists brain_meta_methods(id integer primary key,method text unique,trials integer default 0,historical_wins integer default 0,live_wins integer default 0,transfer_mean real default 0,last_seen text,metadata text)''')
    c.execute('''create table if not exists brain_vault_registry(id integer primary key,vault_key text unique,start_date text,end_date text,status text default 'sealed',opens integer default 0,last_opened text,metadata text)''')
    c.execute('''create table if not exists brain_hall_of_fame(id integer primary key,created_at text,lineage text unique,reason text,score real,metadata text)''')
    c.execute('''create table if not exists brain_graveyard(id integer primary key,created_at text,lineage text unique,reason text,score real,metadata text)''')
    c.commit();c.close()


def epistemic_score(evidence:Iterable[dict])->float:
    num=den=0.0
    for e in evidence:
        tier=e.get('tier','historical_train');w=EPISTEMIC_WEIGHTS.get(tier,0)*math.sqrt(max(1,int(e.get('n',1))))
        # instability/drawdown are explicit penalties; live evidence naturally dominates.
        objective=float(e.get('objective',0));dd=abs(float(e.get('drawdown',0) or 0));s=objective-.15*dd
        num+=w*s;den+=w
    return num/den if den else -1e9


def anti_overfit_score(fold_scores:List[float],complexity:int,regime_scores:Dict[str,float])->float:
    if not fold_scores:return -1e9
    mean=sum(fold_scores)/len(fold_scores);var=sum((x-mean)**2 for x in fold_scores)/len(fold_scores)
    dispersion=math.sqrt(var);reg=list(regime_scores.values());reg_spread=(max(reg)-min(reg)) if len(reg)>1 else 0
    return mean-.35*dispersion-.10*reg_spread-.002*max(0,complexity-5)


def mutate(parent:Candidate,keys:List[str],rng:random.Random,regime:str|None=None)->Candidate:
    w=dict(parent.weights);changed=0
    for k in keys:
        if rng.random()<.45:
            delta=max(-MAX_GENE_STEP,min(MAX_GENE_STEP,rng.gauss(0,MUTATION_SIGMA)));w[k]=max(-.5,min(.5,w.get(k,0)+delta));changed+=1
    dist=sum(abs(w[k]-parent.weights.get(k,0)) for k in keys)
    if dist>MAX_TOTAL_DISTANCE:
        scale=MAX_TOTAL_DISTANCE/dist;w={k:parent.weights.get(k,0)+(w[k]-parent.weights.get(k,0))*scale for k in keys}
    return Candidate(f"{parent.lineage}.g{parent.generation+1}.{rng.randrange(10**7):07d}",parent.generation+1,w,parent.lineage,regime)


def seed_population(champion_version:str,weights:Dict[str,float],regimes:List[str]|None=None,seed:int=42)->List[Candidate]:
    rng=random.Random(seed);base=Candidate(f"champion:{champion_version}",0,dict(weights));out=[base];keys=list(weights);regimes=regimes or []
    while len(out)<POPULATION:
        regime=regimes[(len(out)-1)%len(regimes)] if regimes and len(out)%3==0 else None
        out.append(mutate(base,keys,rng,regime))
    return out


def select_diverse(scored:List[tuple[Candidate,float]],elite:int=ELITE)->List[Candidate]:
    ranked=sorted(scored,key=lambda x:x[1],reverse=True);chosen=[]
    for cand,score in ranked:
        if not chosen:chosen.append(cand);continue
        distance=min(sum(abs(cand.weights.get(k,0)-x.weights.get(k,0)) for k in cand.weights) for x in chosen)
        if distance>=.035 or cand.specialist_regime not in {x.specialist_regime for x in chosen}:chosen.append(cand)
        if len(chosen)>=elite:break
    return chosen


def transfer_score(historical:float,live:float,n_live:int)->float:
    if n_live<=0:return 0.0
    agreement=1.0-min(2.0,abs(live-historical)/(abs(historical)+.05))
    confidence=min(1.0,math.log1p(n_live)/math.log(101))
    return max(-1.0,min(1.0,agreement*confidence))


def record_lineage(candidate:Candidate,status='shadow',reason='',metrics=None):
    init_brain_db();c=con();c.execute('''insert into brain_lineages(created_at,lineage,parent,generation,specialist_regime,weights,status,reason,metrics) values(?,?,?,?,?,?,?,?,?) on conflict(lineage) do update set status=excluded.status,reason=excluded.reason,metrics=excluded.metrics''',(now(),candidate.lineage,candidate.parent,candidate.generation,candidate.specialist_regime,json.dumps(candidate.weights),status,reason,json.dumps(metrics or {})));c.commit();c.close()


def record_evidence(lineage,tier,regime,horizon,n,objective,hit_rate=0,drawdown=0,metadata=None):
    assert tier in EPISTEMIC_WEIGHTS
    init_brain_db();c=con();score=epistemic_score([{'tier':tier,'n':n,'objective':objective,'drawdown':drawdown}]);c.execute('insert into brain_evidence(created_at,lineage,tier,regime,horizon,n,objective,hit_rate,drawdown,score,metadata) values(?,?,?,?,?,?,?,?,?,?,?)',(now(),lineage,tier,regime,horizon,n,objective,hit_rate,drawdown,score,json.dumps(metadata or {})));c.commit();c.close();return score


def promotion_gate(lineage:str,min_live=40)->dict:
    """Final gate. Historical excellence can create a shadow champion, never a live champion by itself."""
    init_brain_db();c=con();rows=c.execute('select tier,n,objective,drawdown from brain_evidence where lineage=?',(lineage,)).fetchall();c.close()
    ev=[{'tier':r[0],'n':r[1],'objective':r[2],'drawdown':r[3]} for r in rows];live=[e for e in ev if e['tier']=='live_forward'];n_live=sum(e['n'] for e in live)
    hist=[e for e in ev if e['tier']!='live_forward'];hist_score=epistemic_score(hist);live_score=epistemic_score(live) if live else None
    return {'lineage':lineage,'historical_score':hist_score,'live_score':live_score,'n_live':n_live,'shadow_eligible':bool(hist),'promotion_eligible':n_live>=min_live and live_score is not None and live_score>0,'real_trading':False}


def brain_dashboard(limit=20):
    init_brain_db();c=con();lineages=[dict(zip(['lineage','parent','generation','regime','status','reason','metrics'],r)) for r in c.execute('select lineage,parent,generation,specialist_regime,status,reason,metrics from brain_lineages order by id desc limit ?',(limit,)).fetchall()]
    transfer=[dict(zip(['lineage','historical','live','transfer','n_live'],r)) for r in c.execute('select lineage,historical_score,live_score,transfer_ratio,n_live from brain_transfer order by id desc limit ?',(limit,)).fetchall()]
    vaults=[dict(zip(['key','start','end','status','opens'],r)) for r in c.execute('select vault_key,start_date,end_date,status,opens from brain_vault_registry order by start_date').fetchall()];c.close()
    return {'epistemic_weights':EPISTEMIC_WEIGHTS,'lineages':lineages,'transfer':transfer,'vaults':vaults,'real_trading':False}
