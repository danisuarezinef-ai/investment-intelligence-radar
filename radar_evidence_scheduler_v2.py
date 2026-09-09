"""Horizon-aware prospective evidence scheduler.

Prioritises due forward outcomes without backfill or retrospective reconstruction.
"""
from __future__ import annotations
from datetime import datetime, timezone

REAL_TRADING=False
HORIZON_PRIORITY={'1d':0,'1w':1,'1m':2,'3m':3}


def _dt(value):
    if isinstance(value,datetime):return value
    return datetime.fromisoformat(str(value).replace('Z','+00:00'))


def schedule_due(rows, now=None, limit=100):
    now=_dt(now or datetime.now(timezone.utc))
    due=[];pending=[]
    for row in rows or []:
        r=dict(row)
        if r.get('backfilled') or r.get('retrospective'):
            r['scheduler_state']='REJECTED_BACKFILL';pending.append(r);continue
        target=r.get('target_at') or r.get('target_date')
        if not target:
            r['scheduler_state']='MISSING_TARGET';pending.append(r);continue
        target_dt=_dt(target)
        if target_dt<=now and str(r.get('outcome_status','PENDING')).upper()=='PENDING':
            r['scheduler_state']='DUE';due.append(r)
        else:
            r['scheduler_state']='WAITING';pending.append(r)
    due.sort(key=lambda r:(HORIZON_PRIORITY.get(str(r.get('horizon')),99),_dt(r.get('target_at') or r.get('target_date'))))
    return {'due':due[:max(0,int(limit))],'waiting':pending,'due_count':len(due),'real_trading':False,'backfill_allowed':False}
