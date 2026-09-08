"""Serious shadow-forward experiment evidence builder.

Reads only the immutable forward ledger and paper/shadow records already persisted.
It does not backfill, does not synthesize benchmark evidence, and never trades.
"""
from __future__ import annotations
import json
from datetime import datetime,timezone
from radar_core import con
from radar_investment_memory import init_memory
from radar_promotion_attribution_v1 import confidence_calibration

REAL_TRADING=False
CONTROL_KEY='shadow_forward_started_at'


def _dt(x):
    if not x:return None
    try:return datetime.fromisoformat(str(x).replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception:return None


def _outcome(raw):
    try:o=json.loads(raw) if isinstance(raw,str) else raw
    except Exception:return None
    if not isinstance(o,dict):return None
    ret=o.get('return_pct')
    if ret is None and o.get('return') is not None:
        try:ret=float(o['return'])*100.0
        except Exception:return None
    try:ret=float(ret)
    except Exception:return None
    return {'return_pct':ret,'hit':ret>0,'exit_price':o.get('exit_price'),'price_timestamp':o.get('price_timestamp')}


def _max_drawdown(returns):
    equity=1.0;peak=1.0;worst=0.0
    for r in returns:
        equity*=1.0+r/100.0;peak=max(peak,equity)
        if peak>0:worst=min(worst,(equity/peak-1.0)*100.0)
    return worst


def shadow_experiment_evidence():
    c=con();init_memory(c)
    boundary_row=c.execute('select value from control where key=?',(CONTROL_KEY,)).fetchone()
    boundary=boundary_row[0] if boundary_row else None;boundary_dt=_dt(boundary)
    rows=c.execute('''select id,created_at,target_date,asset,horizon,model_version,confidence,
                      provenance_snapshot,payload,outcome,evaluated_at
                      from prediction_ledger order by created_at,id''').fetchall()
    decisions=c.execute('select count(*) from decision_journal').fetchone()[0]
    c.close()
    records=[];integrity_errors=[];calibration=[];returns=[];months=set()
    for row in rows:
        pid,created,target,asset,horizon,model,confidence,prov_raw,payload_raw,outcome_raw,evaluated=row
        created_dt=_dt(created);target_dt=_dt(target);eval_dt=_dt(evaluated)
        try:prov=json.loads(prov_raw or '{}')
        except Exception:prov={}
        try:payload=json.loads(payload_raw or '{}')
        except Exception:payload={}
        no_backfill=bool(boundary_dt and created_dt and created_dt>=boundary_dt)
        lookahead_false=prov.get('lookahead') is False
        immutable=payload.get('immutable') is True and payload.get('real_trading') is False
        maturity_order=(outcome_raw is None) or bool(target_dt and eval_dt and eval_dt>=target_dt)
        if not (no_backfill and lookahead_false and immutable and maturity_order):
            integrity_errors.append({'prediction_id':pid,'no_backfill':no_backfill,'lookahead_false':lookahead_false,'immutable':immutable,'maturity_order':maturity_order})
        out=_outcome(outcome_raw) if outcome_raw is not None else None
        matured=out is not None and eval_dt is not None
        rec={'prediction_id':pid,'created_at':created,'evaluated_at':evaluated,'asset':asset,'horizon':horizon,
             'model_version':model,'confidence':confidence,'immutable':immutable,'matured':matured,
             'return_pct':out['return_pct'] if out else None,'no_backfill':no_backfill,'lookahead_false':lookahead_false}
        records.append(rec)
        if out:
            returns.append(out['return_pct']);calibration.append({'confidence':confidence,'hit':out['hit']})
            if eval_dt:months.add(eval_dt.strftime('%Y-%m'))
    first=_dt(boundary);last=max((_dt(r['created_at']) for r in records if _dt(r['created_at'])),default=None)
    forward_days=(last-first).total_seconds()/86400.0 if first and last and last>=first else 0.0
    cal=confidence_calibration(calibration)
    positive_months=0
    if returns and months:
        monthly={m:[] for m in months}
        for r in records:
            if r['return_pct'] is None or not r['evaluated_at']:continue
            d=_dt(r['evaluated_at']);monthly.setdefault(d.strftime('%Y-%m'),[]).append(float(r['return_pct']))
        positive_months=sum(1 for vals in monthly.values() if vals and sum(vals)>0)
    return {'forward_days':forward_days,'predictions':len(records),'matured_predictions':len(returns),'decisions':int(decisions or 0),
            'max_drawdown_pct':_max_drawdown(returns) if returns else None,
            'brier':cal.get('brier'),'hit_rate':cal.get('hit_rate'),
            'excess_return_pct':None,
            'positive_months':positive_months,
            'ledger_integrity':bool(boundary and not integrity_errors),
            'pit_verified':bool(boundary and not integrity_errors),
            'costs_included':False,
            'benchmark_evidence_available':False,
            'integrity_errors':integrity_errors,'records':records,
            'real_trading':False}
