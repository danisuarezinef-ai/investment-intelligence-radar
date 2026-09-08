"""Decision outcome evaluator v4.

Extends forward outcome learning to Champion ABSTAIN decisions by evaluating the
reference top candidate stored in the frozen hypothesis. This lets the system
learn whether abstention avoided a loss or missed a material gain.

Outcomes remain single-assignment and use only recorded market snapshots.
"""
from __future__ import annotations
import json
from radar_core import con, init_db, now
from radar_decision_memory_v2 import init_decision_memory_db, evaluate_episode

REAL_TRADING=False
HORIZON_SESSIONS={'1d':1,'1w':5,'1m':21,'3m':63,'forward':21}
ABSTAIN_NEUTRAL_BAND_PCT=1.0


def _observed_path(symbol,created_at):
    init_db(); c=con(); rows=c.execute('''select x.d,m.price from (
        select substr(ts,1,10) d,min(id) mid from market_snapshots
        where symbol=? and price is not null and ts>=? group by substr(ts,1,10)
      ) x join market_snapshots m on m.id=x.mid order by x.d''',(symbol,created_at)).fetchall(); c.close()
    return [(r[0],float(r[1])) for r in rows if r[1] is not None]


def _reference_symbol(symbol,action,hypothesis_json):
    if symbol:return symbol,'decision_symbol'
    if str(action).upper()!='ABSTAIN':return None,None
    try:h=json.loads(hypothesis_json or '{}')
    except Exception:return None,None
    top=h.get('top') if isinstance(h,dict) else None
    if isinstance(top,dict) and top.get('symbol'):return top['symbol'],'abstain_top_candidate'
    return None,None


def evaluate_mature_episodes_v4(limit=500):
    init_decision_memory_db(); c=con(); rows=c.execute('''select episode_id,created_at,symbol,horizon,action,confidence,hypothesis
      from decision_episodes where outcome is null order by created_at asc limit ?''',(max(1,int(limit)),)).fetchall(); c.close()
    evaluated=pending=skipped=abstain_evaluated=0; errors=[]
    for eid,created,symbol,horizon,action,confidence,hypothesis in rows:
        need=HORIZON_SESSIONS.get(str(horizon or '').lower())
        if not need:skipped+=1; continue
        ref,ref_source=_reference_symbol(symbol,action,hypothesis)
        if not ref:skipped+=1; continue
        path=_observed_path(ref,created)
        if len(path)<=need:pending+=1; continue
        entry_date,entry=path[0]; exit_date,exit_px=path[need]
        if entry<=0:skipped+=1; continue
        ret=(exit_px/entry-1.0)*100.0; act=str(action or '').upper()
        if act in ('PAPER_BUY_CANDIDATE','BUY','PAPER_BUY'):
            reward=ret; hit=ret>0; interpretation='buy_direction'
        elif act in ('PAPER_SELL_CANDIDATE','SELL','PAPER_SELL'):
            reward=-ret; hit=ret<0; interpretation='sell_direction'
        elif act=='ABSTAIN':
            # Positive reward for avoiding a loss; negative only for gains beyond a
            # neutral band so tiny/noisy upside does not punish prudent abstention.
            reward=(-ret if ret<0 else -max(0.0,ret-ABSTAIN_NEUTRAL_BAND_PCT))
            hit=ret<=ABSTAIN_NEUTRAL_BAND_PCT; interpretation='abstain_opportunity_cost'
            abstain_evaluated+=1
        else:skipped+=1; continue
        outcome={'return_pct':ret,'reward':reward,'hit':bool(hit),'entry_price':entry,'exit_price':exit_px,'entry_date':entry_date,'exit_date':exit_date,'sessions':need,'source':'recorded_market_snapshots','reference_symbol':ref,'reference_source':ref_source,'interpretation':interpretation,'neutral_band_pct':ABSTAIN_NEUTRAL_BAND_PCT if act=='ABSTAIN' else None,'real_trading':False}
        lesson=('decision validated' if hit else 'decision not validated')+f'; action={act}; confidence={float(confidence or 0):.3f}; observed_return={ret:.3f}%'
        try:evaluate_episode(eid,outcome,lesson=lesson,evaluated_at=now()); evaluated+=1
        except Exception as exc:errors.append({'episode_id':eid,'error':str(exc)})
    return {'evaluated':evaluated,'abstain_evaluated':abstain_evaluated,'pending':pending,'skipped':skipped,'errors':errors[:20],'neutral_band_pct':ABSTAIN_NEUTRAL_BAND_PCT,'real_trading':False}
