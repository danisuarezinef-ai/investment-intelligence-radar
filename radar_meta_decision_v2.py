"""Adaptive Champion decision layer. Simulation/paper only; can abstain."""
from __future__ import annotations
import math,json
from radar_core import opportunity_rankings,now
from radar_agents import agents_status,AGENTS
from radar_decision_memory_v2 import record_episode,retrieve_similar,memory_health

REAL_TRADING=False


def _agent_quality(st):
    if not st.get('configured'):return 0.0
    sharpe=max(-2.0,min(3.0,float(st.get('sharpe') or 0)))
    dd=abs(float(st.get('max_drawdown_pct') or 0))
    pnl=float(st.get('pnl_pct') or 0)
    # bounded, deliberately conservative; forward evidence should dominate later.
    return max(0.05,min(1.5,0.55+0.12*sharpe+0.01*max(-10,min(20,pnl))-0.015*min(30,dd)))


def _memory_adjust(symbol,risk,horizon='1m'):
    eps=retrieve_similar(symbol=symbol,horizon=horizon,tags=['champion'],limit=20)
    vals=[]
    for e in eps:
        out=e.get('outcome') or {}
        if isinstance(out,dict):
            for key in ('alpha_pct','return_pct','reward','pnl_pct'):
                if out.get(key) is not None:
                    try:vals.append(float(out[key]));break
                    except Exception:pass
    if not vals:return 0.0,0
    mean=sum(vals)/len(vals)
    return max(-8.0,min(8.0,mean))*0.12,len(vals)


def champion_decision(limit=8,horizon='1m',record=True):
    rankings=opportunity_rankings(max(12,limit))
    flat=[r for tier in rankings.values() for r in tier]
    if not flat:
        return {'action':'ABSTAIN','reason':'insufficient_market_history','confidence':0.0,'candidates':[],'real_trading':False}
    statuses={x['agent_id']:x for x in agents_status() if x.get('configured')}
    weights={aid:_agent_quality(st) for aid,st in statuses.items()}
    total_w=sum(weights.values()) or 1.0
    rows=[]
    for r in flat:
        base=float(r['score']); risk=r['risk']; support=0.0; voters=0
        for aid,cfg in AGENTS.items():
            w=weights.get(aid,0.0)
            if not w:continue
            eligible=risk in cfg['tiers'] and base>=cfg['min_score']
            vote=1.0 if eligible else -0.35
            support+=w*vote;voters+=1
        consensus=support/total_w
        mem,nmem=_memory_adjust(r['symbol'],risk,horizon)
        risk_penalty={'bajo':0.0,'intermedio':1.2,'alto':3.0}.get(risk,1.5)
        champion_score=base+4.0*consensus+mem-risk_penalty
        rows.append({**r,'champion_score':champion_score,'consensus':consensus,'memory_adjustment':mem,'memory_n':nmem})
    rows.sort(key=lambda x:x['champion_score'],reverse=True);rows=rows[:limit]
    scores=[x['champion_score'] for x in rows]
    disagreement=(max(scores)-min(scores)) if len(scores)>1 else 0.0
    top=rows[0]
    conf=max(0.0,min(1.0,0.50+0.06*top['champion_score']+0.20*max(-1,min(1,top['consensus']))-0.015*disagreement))
    abstain=conf<0.48 or top['champion_score']<=0 or top['consensus']<0
    action='ABSTAIN' if abstain else 'PAPER_BUY_CANDIDATE'
    allocation=0.0 if abstain else max(0.02,min(0.18,0.04+0.12*conf))
    result={'ts':now(),'action':action,'symbol':None if abstain else top['symbol'],'confidence':conf,'allocation_fraction':allocation,'disagreement':disagreement,'candidates':rows,'agent_weights':weights,'reason':('low confidence/disagreement' if abstain else 'weighted multi-agent consensus with risk and memory adjustment'),'real_trading':False}
    if record:
        result['episode_id']=record_episode(agent_id='champion',symbol=result['symbol'],horizon=horizon,regime=None,state={'rankings_top':rows[:5],'agent_weights':weights},evidence={'source':'opportunity_rankings+paper_agents+decision_memory','disagreement':disagreement},hypothesis={'top':top},action=action,confidence=conf,alternatives=[x['symbol'] for x in rows[1:4]],allocation={'fraction':allocation},reason=result['reason'],tags=['champion','automatic_decision','simulation'])
    return result


def champion_health():
    st=agents_status();return {'agents':len(st),'weights':{x['agent_id']:_agent_quality(x) for x in st if x.get('configured')},'memory':memory_health(),'real_trading':False}
