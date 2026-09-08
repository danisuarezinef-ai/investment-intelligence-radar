"""Adaptive Champion decision layer. Simulation/paper only; can abstain."""
from __future__ import annotations
import math
from radar_core import opportunity_rankings,now
from radar_agents import agents_status,AGENTS
from radar_decision_memory_v2 import record_episode,retrieve_similar,memory_health
from radar_learning_v2 import agent_skill_table
from radar_learning import detect_regime

REAL_TRADING=False


def _base_agent_quality(st):
    if not st.get('configured'):return 0.0
    sharpe=max(-2.0,min(3.0,float(st.get('sharpe') or 0)))
    dd=abs(float(st.get('max_drawdown_pct') or 0))
    pnl=float(st.get('pnl_pct') or 0)
    return max(0.05,min(1.5,0.55+0.12*sharpe+0.01*max(-10,min(20,pnl))-0.015*min(30,dd)))


def _skill_row(agent_id,regime,horizon='forward'):
    rows=agent_skill_table(200)
    exact=[r for r in rows if r.get('agent_id')==agent_id and r.get('regime')==regime and r.get('horizon')==horizon]
    if exact:return exact[0]
    fallback=[r for r in rows if r.get('agent_id')==agent_id and r.get('horizon')==horizon and r.get('regime') in ('unknown','mixed')]
    if fallback:return fallback[0]
    anyrow=[r for r in rows if r.get('agent_id')==agent_id and r.get('horizon')==horizon]
    return anyrow[0] if anyrow else None


def _agent_quality(st,regime='mixed'):
    base=_base_agent_quality(st); row=_skill_row(st.get('agent_id'),regime)
    if not row:return base,{'source':'paper_only','n':0,'score':None,'multiplier':1.0}
    n=max(0,int(row.get('n') or 0)); score=float(row.get('score') or 0)
    evidence=min(1.0,n/40.0)
    multiplier=max(.75,min(1.25,1.0+.25*math.tanh(score/2.0)*evidence))
    return max(.03,min(1.8,base*multiplier)),{'source':'paper+learned_skill','n':n,'score':score,'multiplier':multiplier,'regime':row.get('regime')}


def _memory_adjust(symbol,regime,horizon='1m'):
    eps=retrieve_similar(symbol=symbol,regime=regime,horizon=horizon,tags=['champion'],limit=24)
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
    confidence=min(1.0,len(vals)/20.0)
    return max(-8.0,min(8.0,mean))*0.12*confidence,len(vals)


def champion_decision(limit=8,horizon='1m',record=True):
    regime_info=detect_regime(store=False); regime=regime_info.get('regime') or 'mixed'
    rankings=opportunity_rankings(max(12,limit)); flat=[r for tier in rankings.values() for r in tier]
    if not flat:
        return {'action':'ABSTAIN','reason':'insufficient_market_history','confidence':0.0,'candidates':[],'regime':regime,'real_trading':False}
    statuses={x['agent_id']:x for x in agents_status() if x.get('configured')}
    weights={}; skill_context={}
    for aid,st in statuses.items():
        q,ctx=_agent_quality(st,regime); weights[aid]=q; skill_context[aid]=ctx
    total_w=sum(weights.values()) or 1.0
    rows=[]
    for r in flat:
        base=float(r['score']); risk=r['risk']; support=0.0
        for aid,cfg in AGENTS.items():
            w=weights.get(aid,0.0)
            if not w:continue
            eligible=risk in cfg['tiers'] and base>=cfg['min_score']
            support+=w*(1.0 if eligible else -0.35)
        consensus=support/total_w
        mem,nmem=_memory_adjust(r['symbol'],regime,horizon)
        risk_penalty={'bajo':0.0,'intermedio':1.2,'alto':3.0}.get(risk,1.5)
        champion_score=base+4.0*consensus+mem-risk_penalty
        rows.append({**r,'champion_score':champion_score,'consensus':consensus,'memory_adjustment':mem,'memory_n':nmem})
    rows.sort(key=lambda x:x['champion_score'],reverse=True);rows=rows[:limit]
    scores=[x['champion_score'] for x in rows]; disagreement=(max(scores)-min(scores)) if len(scores)>1 else 0.0; top=rows[0]
    regime_conf=float(regime_info.get('confidence') or .5)
    conf=max(0.0,min(1.0,0.45+0.06*top['champion_score']+0.18*max(-1,min(1,top['consensus']))+0.08*(regime_conf-.5)-0.015*disagreement))
    abstain=conf<0.50 or top['champion_score']<=0 or top['consensus']<0
    action='ABSTAIN' if abstain else 'PAPER_BUY_CANDIDATE'; allocation=0.0 if abstain else max(0.02,min(0.18,0.03+0.12*conf))
    result={'ts':now(),'action':action,'symbol':None if abstain else top['symbol'],'confidence':conf,'allocation_fraction':allocation,'disagreement':disagreement,'candidates':rows,'agent_weights':weights,'agent_skill_context':skill_context,'regime':regime,'regime_confidence':regime_conf,'reason':('low confidence/disagreement' if abstain else 'regime-aware weighted consensus using learned agent skill and episodic memory'),'real_trading':False}
    if record:
        result['episode_id']=record_episode(agent_id='champion',symbol=result['symbol'],horizon=horizon,regime=regime,state={'rankings_top':rows[:5],'agent_weights':weights,'agent_skill_context':skill_context,'regime':regime_info},evidence={'source':'opportunity_rankings+paper_agents+learned_skill+decision_memory','disagreement':disagreement},hypothesis={'top':top},action=action,confidence=conf,alternatives=[x['symbol'] for x in rows[1:4]],allocation={'fraction':allocation},reason=result['reason'],tags=['champion','automatic_decision','simulation','regime:'+regime])
    return result


def champion_health():
    regime=detect_regime(store=False); st=agents_status(); weights={}; ctx={}
    for x in st:
        if x.get('configured'):
            q,c=_agent_quality(x,regime.get('regime') or 'mixed');weights[x['agent_id']]=q;ctx[x['agent_id']]=c
    return {'agents':len(st),'regime':regime,'weights':weights,'skill_context':ctx,'memory':memory_health(),'real_trading':False}
