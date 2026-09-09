"""Provider resilience and failover policy v1.

Pure policy module used to decide provider order from observed health. It never
fabricates provider success and contains no network credentials or trading path.
"""
from __future__ import annotations

REAL_TRADING=False

DEFAULT_POLICY={
    'failure_threshold':3,
    'cooldown_seconds':300,
    'max_error_rate':0.35,
}


def provider_health(provider, policy=None):
    p={**DEFAULT_POLICY, **(policy or {})}; x=provider or {}
    calls=int(x.get('calls') or 0); failures=int(x.get('failures') or 0)
    consecutive=int(x.get('consecutive_failures') or 0)
    error_rate=(failures/calls) if calls>0 else None
    cooldown=bool(x.get('cooldown_active',False))
    if calls<=0:
        status='UNKNOWN'
    elif cooldown or consecutive>=int(p['failure_threshold']):
        status='OPEN_CIRCUIT'
    elif error_rate is not None and error_rate>float(p['max_error_rate']):
        status='DEGRADED'
    else:
        status='HEALTHY'
    return {'name':x.get('name'),'status':status,'calls':calls,'failures':failures,
            'error_rate':error_rate,'consecutive_failures':consecutive,'cooldown_active':cooldown,
            'real_trading':False}


def failover_order(providers, policy=None):
    health=[provider_health(x,policy) for x in (providers or [])]
    rank={'HEALTHY':0,'UNKNOWN':1,'DEGRADED':2,'OPEN_CIRCUIT':3}
    ordered=sorted(health,key=lambda x:(rank[x['status']], x.get('error_rate') if x.get('error_rate') is not None else 1.0, str(x.get('name'))))
    usable=[x for x in ordered if x['status']!='OPEN_CIRCUIT']
    return {'providers':ordered,'request_order':[x['name'] for x in usable if x.get('name')],
            'all_unavailable':len(usable)==0,'fail_closed':len(usable)==0,'real_trading':False}


def source_consensus(quotes, max_deviation_pct=1.5):
    vals=[float(q['price']) for q in (quotes or []) if q.get('price') is not None and float(q['price'])>0]
    if len(vals)<2:
        return {'status':'INSUFFICIENT_EVIDENCE','consensus_price':None,'real_trading':False}
    vals=sorted(vals); med=vals[len(vals)//2] if len(vals)%2 else (vals[len(vals)//2-1]+vals[len(vals)//2])/2
    deviations=[abs(v/med-1.0)*100.0 for v in vals]
    ok=max(deviations)<=float(max_deviation_pct)
    return {'status':'OK' if ok else 'CONFLICT','consensus_price':med if ok else None,
            'max_deviation_pct':max(deviations),'sources':len(vals),'real_trading':False}
