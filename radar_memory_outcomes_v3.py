"""Forward-only evaluator for mature decision-memory episodes.

Uses market observations recorded after each decision. It never fabricates prices,
never assigns an outcome twice, and never evaluates before enough observed market
sessions exist for the configured horizon.
"""
from __future__ import annotations
from radar_core import con, init_db, now
from radar_decision_memory_v2 import init_decision_memory_db, evaluate_episode

REAL_TRADING=False
HORIZON_SESSIONS={'1d':1,'1w':5,'1m':21,'3m':63,'forward':21}


def _observed_path(symbol, created_at):
    """Return the first recorded observation for each market date deterministically."""
    init_db(); c=con()
    rows=c.execute('''select x.d,m.price
                      from (
                        select substr(ts,1,10) d,min(id) mid
                        from market_snapshots
                        where symbol=? and price is not null and ts>=?
                        group by substr(ts,1,10)
                      ) x
                      join market_snapshots m on m.id=x.mid
                      order by x.d''',(symbol,created_at)).fetchall()
    c.close(); return [(r[0],float(r[1])) for r in rows if r[1] is not None]


def evaluate_mature_episodes(limit=250):
    init_decision_memory_db(); c=con()
    rows=c.execute('''select episode_id,created_at,symbol,horizon,action,confidence
                      from decision_episodes
                      where outcome is null and symbol is not null
                      order by created_at asc limit ?''',(max(1,int(limit)),)).fetchall()
    c.close(); evaluated=0; pending=0; skipped=0; errors=[]
    for eid,created,symbol,horizon,action,confidence in rows:
        need=HORIZON_SESSIONS.get(str(horizon or '').lower())
        if not need:
            skipped+=1; continue
        path=_observed_path(symbol,created)
        if len(path)<=need:
            pending+=1; continue
        entry_date,entry=path[0]; exit_date,exit_px=path[need]
        if entry<=0:
            skipped+=1; continue
        ret=(exit_px/entry-1.0)*100.0
        if action in ('PAPER_BUY_CANDIDATE','BUY','PAPER_BUY'):
            reward=ret; hit=ret>0
        elif action in ('PAPER_SELL_CANDIDATE','SELL','PAPER_SELL'):
            reward=-ret; hit=ret<0
        else:
            skipped+=1; continue
        outcome={'return_pct':ret,'reward':reward,'hit':bool(hit),'entry_price':entry,'exit_price':exit_px,'entry_date':entry_date,'exit_date':exit_date,'sessions':need,'source':'recorded_market_snapshots','real_trading':False}
        lesson=('decision direction confirmed' if hit else 'decision direction not confirmed')+f'; confidence={float(confidence or 0):.3f}'
        try:
            evaluate_episode(eid,outcome,lesson=lesson,evaluated_at=now()); evaluated+=1
        except Exception as exc:
            errors.append({'episode_id':eid,'error':str(exc)})
    return {'evaluated':evaluated,'pending':pending,'skipped':skipped,'errors':errors[:20],'real_trading':False}
