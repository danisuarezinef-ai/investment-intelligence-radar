"""Forward attribution v3. Requires explicit benchmark and costs; no inferred zeros."""
from __future__ import annotations

REAL_TRADING=False


def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None


def attribute_trade_v3(record):
    r=record or {}
    gross=_f(r.get('gross_return_pct',r.get('return_pct')))
    benchmark=_f(r.get('benchmark_return_pct'))
    costs=_f(r.get('costs_pct'))
    if None in (gross,benchmark,costs):
        return {'attributable':False,'reason':'gross_benchmark_or_cost_missing','real_trading':False}
    net=gross-costs
    selection=net-benchmark
    factors={k:_f(r.get(k)) for k in ('timing_effect_pct','sizing_effect_pct','fx_effect_pct','sector_effect_pct','beta_effect_pct','cash_effect_pct')}
    known=sum(v for v in factors.values() if v is not None)
    residual=selection-known
    return {'attributable':True,'gross_return_pct':gross,'costs_pct':costs,'net_return_pct':net,'benchmark_return_pct':benchmark,'selection_excess_pct':selection,'factors':factors,'residual_pct':residual,'full_decomposition':all(v is not None for v in factors.values()),'real_trading':False}


def attribution_summary_v3(records):
    rows=[attribute_trade_v3(r) for r in (records or [])]
    ok=[r for r in rows if r.get('attributable')]
    n=len(rows); m=len(ok)
    return {'records':n,'attributable':m,'coverage':(m/n if n else 0.0),'mean_net_pct':(sum(r['net_return_pct'] for r in ok)/m if m else None),'mean_excess_pct':(sum(r['selection_excess_pct'] for r in ok)/m if m else None),'performance_verified':False,'note':'Forward attribution only; aggregate strategy performance requires matured immutable prospective evidence.','real_trading':False}
