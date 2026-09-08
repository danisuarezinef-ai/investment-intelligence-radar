"""Derived statistical consolidation for immutable decision episodes.

The episodic journal stays append-only. This module builds reproducible summaries
from evaluated episodes so sparse memories cannot dominate Champion decisions.
No synthetic outcomes are created and REAL_TRADING remains disabled.
"""
from __future__ import annotations
import json,math,statistics
from radar_core import con,init_db,now
from radar_decision_memory_v2 import init_decision_memory_db

REAL_TRADING=False
BETA_ALPHA=2.0
BETA_BETA=2.0
REWARD_SHRINK_N=10.0
RELIABILITY_N=12.0


def init_consolidation_db():
    init_decision_memory_db();c=con()
    c.execute('''create table if not exists decision_memory_patterns(
      pattern_key text primary key,agent_id text,action text,horizon text,regime text,symbol text,
      specificity integer not null,n integer not null,wins integer not null,losses integer not null,
      mean_reward real,shrunk_reward real,posterior_hit_rate real,mean_confidence real,brier real,
      downside_mean real,reliability real,updated_at text not null,metadata text)''')
    c.execute('create index if not exists idx_memory_patterns_lookup on decision_memory_patterns(agent_id,action,horizon,regime,symbol,specificity)')
    c.commit();c.close()


def _outcome(raw):
    try:o=json.loads(raw) if isinstance(raw,str) else raw
    except Exception:return None
    if not isinstance(o,dict):return None
    reward=None
    for k in ('reward','alpha_pct','return_pct','pnl_pct'):
        if o.get(k) is not None:
            try:reward=float(o[k]);break
            except Exception:pass
    if reward is None:return None
    hit=o.get('hit')
    if hit is None:hit=reward>0
    return {'reward':reward,'hit':bool(hit)}


def _specs(agent,action,horizon,regime,symbol):
    """Nested patterns from broad to specific; no hidden feature generation."""
    return [
      (1,agent,action,None,None,None),
      (2,agent,action,horizon,None,None),
      (3,agent,action,horizon,regime,None),
      (4,agent,action,horizon,regime,symbol),
    ]


def _key(spec,agent,action,horizon,regime,symbol):
    vals=[str(spec),agent or '*',action or '*',horizon or '*',regime or '*',symbol or '*']
    return '|'.join(vals)


def consolidate_memory():
    """Rebuild all derived patterns deterministically from evaluated episodes."""
    init_consolidation_db();c=con();rows=c.execute('''select agent_id,action,horizon,regime,symbol,confidence,outcome
      from decision_episodes where outcome is not null order by created_at,episode_id''').fetchall();groups={}
    used=0
    for agent,action,horizon,regime,symbol,confidence,raw in rows:
        out=_outcome(raw)
        if not out:continue
        used+=1
        for spec,a,act,hor,reg,sym in _specs(agent,action,horizon,regime,symbol):
            k=_key(spec,a,act,hor,reg,sym);groups.setdefault(k,{'spec':spec,'agent':a,'action':act,'horizon':hor,'regime':reg,'symbol':sym,'vals':[]})['vals'].append((out['reward'],out['hit'],float(confidence or 0)))
    c.execute('delete from decision_memory_patterns');stamp=now()
    for k,g in groups.items():
        vals=g['vals'];n=len(vals);wins=sum(1 for _,hit,_ in vals if hit);losses=n-wins;rewards=[x[0] for x in vals];confs=[max(0,min(1,x[2])) for x in vals];hits=[1.0 if x[1] else 0.0 for x in vals]
        mean_reward=statistics.mean(rewards);shrunk_reward=mean_reward*(n/(n+REWARD_SHRINK_N));posterior=(wins+BETA_ALPHA)/(n+BETA_ALPHA+BETA_BETA);brier=statistics.mean((conf-hit)**2 for conf,hit in zip(confs,hits));down=[x for x in rewards if x<0];downside=statistics.mean(down) if down else 0.0;sample_rel=1.0-math.exp(-n/RELIABILITY_N);cal_rel=max(.25,1.0-min(1.0,brier));reliability=max(0,min(1,sample_rel*cal_rel))
        c.execute('''insert into decision_memory_patterns(pattern_key,agent_id,action,horizon,regime,symbol,specificity,n,wins,losses,mean_reward,shrunk_reward,posterior_hit_rate,mean_confidence,brier,downside_mean,reliability,updated_at,metadata)
          values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(k,g['agent'],g['action'],g['horizon'],g['regime'],g['symbol'],g['spec'],n,wins,losses,mean_reward,shrunk_reward,posterior,statistics.mean(confs),brier,downside,reliability,stamp,json.dumps({'beta_prior':[BETA_ALPHA,BETA_BETA],'reward_shrink_n':REWARD_SHRINK_N},sort_keys=True)))
    c.commit();c.close();return {'episodes_used':used,'patterns':len(groups),'real_trading':False}


def pattern_prior(*,agent_id='champion',action=None,horizon=None,regime=None,symbol=None,min_n=2):
    """Blend matching patterns with specificity and reliability weighting.

    Returns a conservative prior. Small samples are shrunk toward neutral.
    """
    init_consolidation_db();c=con();rows=c.execute('''select pattern_key,action,horizon,regime,symbol,specificity,n,shrunk_reward,posterior_hit_rate,brier,downside_mean,reliability
      from decision_memory_patterns where agent_id=? order by specificity desc,n desc''',(agent_id,)).fetchall();c.close();matches=[]
    for r in rows:
        _,act,hor,reg,sym,spec,n,reward,hit,brier,down,rel=r
        if int(n or 0)<int(min_n):continue
        if act is not None and action is not None and act!=action:continue
        if act is not None and action is None:continue
        if hor is not None and hor!=horizon:continue
        if reg is not None and reg!=regime:continue
        if sym is not None and sym!=symbol:continue
        weight=float(rel or 0)*(1.0+.35*(int(spec)-1))*math.log1p(int(n))
        if weight<=0:continue
        matches.append({'pattern_key':r[0],'specificity':int(spec),'n':int(n),'reward':float(reward or 0),'hit_rate':float(hit or .5),'brier':float(brier or 0),'downside_mean':float(down or 0),'reliability':float(rel or 0),'weight':weight})
    if not matches:return {'available':False,'expected_reward':0.0,'hit_rate':.5,'brier':None,'downside_mean':0.0,'reliability':0.0,'effective_n':0,'patterns':[],'real_trading':False}
    sw=sum(x['weight'] for x in matches);avg=lambda k:sum(x[k]*x['weight'] for x in matches)/sw
    reliability=min(1.0,sum(x['reliability']*x['weight'] for x in matches)/sw);effective_n=sum(x['n'] for x in matches)
    return {'available':True,'expected_reward':avg('reward'),'hit_rate':avg('hit_rate'),'brier':avg('brier'),'downside_mean':avg('downside_mean'),'reliability':reliability,'effective_n':effective_n,'patterns':matches[:6],'real_trading':False}


def consolidation_health():
    init_consolidation_db();c=con();row=c.execute('select count(*),sum(n),max(updated_at) from decision_memory_patterns').fetchone();top=c.execute('''select agent_id,action,horizon,regime,symbol,specificity,n,shrunk_reward,posterior_hit_rate,brier,reliability from decision_memory_patterns order by reliability desc,n desc limit 20''').fetchall();c.close()
    return {'patterns':row[0] or 0,'pattern_observations':row[1] or 0,'updated_at':row[2],'top':[{'agent_id':r[0],'action':r[1],'horizon':r[2],'regime':r[3],'symbol':r[4],'specificity':r[5],'n':r[6],'shrunk_reward':r[7],'posterior_hit_rate':r[8],'brier':r[9],'reliability':r[10]} for r in top],'real_trading':False}
