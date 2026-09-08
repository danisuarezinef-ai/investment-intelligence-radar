"""Point-in-time benchmark and explicit cost evidence for shadow validation."""
from __future__ import annotations
import json, statistics
from radar_core import con, ASSETS

REAL_TRADING=False


def _price_at_or_before(c,symbol,stamp):
    r=c.execute('select price,ts from market_snapshots where symbol=? and ts<=? and price is not null order by ts desc,id desc limit 1',(symbol,stamp)).fetchone()
    return (float(r[0]),r[1]) if r and r[0] else None


def _price_at_or_after(c,symbol,stamp):
    r=c.execute('select price,ts from market_snapshots where symbol=? and ts>=? and price is not null order by ts,id limit 1',(symbol,stamp)).fetchone()
    return (float(r[0]),r[1]) if r and r[0] else None


def equal_weight_benchmark(created_at,target_date,min_constituents=8):
    """Equal-weight universe return over the same frozen prediction window."""
    c=con();rows=[]
    for sym in ASSETS:
        a=_price_at_or_before(c,sym,created_at);b=_price_at_or_after(c,sym,target_date)
        if a and b and a[0]>0:
            rows.append({'symbol':sym,'entry_price':a[0],'entry_ts':a[1],'exit_price':b[0],'exit_ts':b[1],'return_pct':(b[0]/a[0]-1)*100.0})
    c.close()
    if len(rows)<int(min_constituents):
        return {'available':False,'constituents':len(rows),'required':int(min_constituents),'return_pct':None,'rows':rows,'real_trading':False}
    return {'available':True,'constituents':len(rows),'required':int(min_constituents),'return_pct':statistics.mean(r['return_pct'] for r in rows),'rows':rows,'method':'equal_weight_ASSETS_same_window','real_trading':False}


def explicit_cost_evidence(payload_raw=None,outcome_raw=None):
    """Accept costs only when explicitly persisted; never assumes a fee schedule."""
    def obj(x):
        if isinstance(x,dict):return x
        try:return json.loads(x or '{}')
        except Exception:return {}
    payload=obj(payload_raw);outcome=obj(outcome_raw)
    vals=[]
    for source,name in ((payload,'payload'),(outcome,'outcome')):
        for key in ('costs_pct','total_cost_pct','realized_cost_pct'):
            if source.get(key) is not None:
                try:vals.append((float(source[key]),name+':'+key))
                except Exception:pass
    if not vals:return {'available':False,'costs_pct':None,'source':None,'real_trading':False}
    value,source=vals[-1]
    return {'available':True,'costs_pct':value,'source':source,'real_trading':False}


def benchmarked_forward_record(record,min_constituents=8):
    bench=equal_weight_benchmark(record['created_at'],record['target_date'],min_constituents)
    costs=explicit_cost_evidence(record.get('payload'),record.get('outcome'))
    gross=record.get('return_pct')
    try:gross=float(gross) if gross is not None else None
    except Exception:gross=None
    net=(gross-costs['costs_pct']) if gross is not None and costs['available'] else None
    excess=(net-bench['return_pct']) if net is not None and bench['available'] else None
    return {'benchmark':bench,'costs':costs,'gross_return_pct':gross,'net_return_pct':net,'excess_return_pct':excess,'fully_attributable':bool(bench['available'] and costs['available'] and gross is not None),'real_trading':False}
