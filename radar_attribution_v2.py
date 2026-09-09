"""Forward-only performance attribution v2. No trading capability."""
from __future__ import annotations
REAL_TRADING=False

def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None

def attribute_record(record):
    r=record or {}; gross=_f(r.get('gross_return_pct',r.get('return_pct'))); bench=_f(r.get('benchmark_return_pct')); costs=_f(r.get('costs_pct'))
    if gross is None:return {'attributable':False,'reason':'gross_return_missing','real_trading':False}
    if bench is None:return {'attributable':False,'reason':'benchmark_missing','real_trading':False}
    if costs is None:return {'attributable':False,'reason':'costs_missing','real_trading':False}
    net=gross-costs; selection=net-bench
    out={'attributable':True,'gross_return_pct':gross,'costs_pct':costs,'net_return_pct':net,'benchmark_return_pct':bench,'selection_excess_pct':selection,'real_trading':False}
    for k in ('timing_effect_pct','sizing_effect_pct','fx_effect_pct','sector_effect_pct'):
        out[k]=_f(r.get(k))
    out['full_decomposition']=all(out[k] is not None for k in ('timing_effect_pct','sizing_effect_pct','fx_effect_pct','sector_effect_pct'))
    return out

def attribution_summary(records):
    rows=[attribute_record(r) for r in (records or [])]; good=[r for r in rows if r['attributable']]
    def mean(k):
        vals=[r[k] for r in good if r.get(k) is not None]; return sum(vals)/len(vals) if vals else None
    return {'records':len(rows),'attributable':len(good),'coverage':len(good)/len(rows) if rows else 0.0,
            'mean_net_return_pct':mean('net_return_pct'),'mean_selection_excess_pct':mean('selection_excess_pct'),
            'full_decomposition_records':sum(1 for r in good if r['full_decomposition']),
            'performance_verified':False,'verification_note':'Requires matured immutable forward records; this function does not assert strategy performance.',
            'rows':rows,'real_trading':False}
