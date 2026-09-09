"""Experiment memory, diversity control and safe stage funnel."""
from __future__ import annotations
import json,hashlib
from radar_core import con,init_db,now
REAL_TRADING=False


def init_memory():
    init_db();c=con();c.execute('''create table if not exists experiment_memory(
      experiment_hash text primary key,created_at text not null,last_seen_at text not null,
      configuration text not null,status text not null,reason text,generation integer not null default 0,
      research_score real,stage text not null default 'SIMULATED')''');c.commit();c.close()


def config_hash(config):return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def remember(config,*,status,reason=None,generation=0,research_score=None,stage='SIMULATED'):
    init_memory();h=config_hash(config);c=con();ts=now();payload=json.dumps(config,sort_keys=True)
    c.execute('insert into experiment_memory(experiment_hash,created_at,last_seen_at,configuration,status,reason,generation,research_score,stage) values(?,?,?,?,?,?,?,?,?) on conflict(experiment_hash) do update set last_seen_at=excluded.last_seen_at,status=excluded.status,reason=excluded.reason,research_score=excluded.research_score,stage=excluded.stage',(h,ts,ts,payload,status,reason,int(generation),research_score,stage));c.commit();c.close();return h


def seen(config):
    init_memory();c=con();row=c.execute('select status,stage,reason from experiment_memory where experiment_hash=?',(config_hash(config),)).fetchone();c.close();return {'seen':bool(row),'status':row[0] if row else None,'stage':row[1] if row else None,'reason':row[2] if row else None,'real_trading':False}


def diversity_filter(experiments,max_same_family=2):
    counts={};out=[]
    for e in experiments or []:
        cfg=e.get('configuration') or {};family=(int(cfg.get('lookback_fast',0)//10),int(cfg.get('lookback_slow',0)//20),round(float(cfg.get('fast_weight',0)),1))
        if counts.get(family,0)>=int(max_same_family):continue
        if seen(cfg)['seen']:continue
        counts[family]=counts.get(family,0)+1;out.append(e)
    return out


def stage_funnel(*,research_gate='REJECT',shadow_forward_n=0,shadow_days=0,paper_forward_n=0,paper_days=0,degradation_clear=False):
    if research_gate!='PASS_RESEARCH':stage='GRAVEYARD';blockers=['RESEARCH_NOT_ROBUST']
    elif int(shadow_forward_n)<20 or int(shadow_days)<7:stage='SHADOW';blockers=['SHADOW_FORWARD_EVIDENCE_REQUIRED']
    elif int(paper_forward_n)<40 or int(paper_days)<14 or not degradation_clear:stage='PAPER_REVIEW';blockers=['PAPER_FORWARD_MATURITY_REQUIRED']
    else:stage='PAPER_MATURE';blockers=[]
    return {'stage':stage,'blockers':blockers,'automatic_live_promotion':False,'real_trading':False}


def memory_snapshot(limit=25):
    init_memory();c=con();rows=c.execute('select experiment_hash,created_at,last_seen_at,status,reason,generation,research_score,stage from experiment_memory order by last_seen_at desc limit ?',(int(limit),)).fetchall();c.close()
    return {'count':len(rows),'experiments':[{'hash':r[0],'created_at':r[1],'last_seen_at':r[2],'status':r[3],'reason':r[4],'generation':r[5],'research_score':r[6],'stage':r[7]} for r in rows],'real_trading':False}
