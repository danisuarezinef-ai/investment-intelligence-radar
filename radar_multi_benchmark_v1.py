"""Multiple benchmark comparison for matured prospective records."""
from __future__ import annotations

REAL_TRADING=False


def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None


def compare_benchmarks(records, benchmark_keys=None):
    keys=list(benchmark_keys or ['global','regional','sector','cash'])
    out={k:{'covered':0,'sum_excess':0.0} for k in keys}; matured=0
    for r in records or []:
        if not (r.get('immutable') is True and r.get('matured') is True and r.get('backfilled') is not True):continue
        ret=_f(r.get('net_return_pct',r.get('return_pct')))
        if ret is None:continue
        matured += 1
        bm=r.get('benchmarks') if isinstance(r.get('benchmarks'),dict) else {}
        for k in keys:
            b=_f(bm.get(k))
            if b is None:continue
            out[k]['covered'] += 1; out[k]['sum_excess'] += ret-b
    rows=[]
    for k in keys:
        c=out[k]['covered']
        rows.append({'benchmark':k,'coverage':(c/matured if matured else 0.0),'covered':c,'matured':matured,'mean_excess_pct':(out[k]['sum_excess']/c if c else None),'status':'AVAILABLE' if c else 'INSUFFICIENT_EVIDENCE'})
    return {'benchmarks':rows,'matured_records':matured,'performance_verified':False,'note':'Comparison requires matured prospective evidence; no missing benchmark is treated as zero.','real_trading':False}


def benchmark_gate(summary,min_coverage=0.95):
    rows=(summary or {}).get('benchmarks') or []
    usable=[r for r in rows if float(r.get('coverage') or 0)>=min_coverage and r.get('mean_excess_pct') is not None]
    return {'passed':bool(usable) and all(float(r['mean_excess_pct'])>=0 for r in usable),'usable_benchmarks':[r['benchmark'] for r in usable],'policy_note':'Coverage threshold is a governance default, NOT empirically validated as optimal.','real_trading':False}
