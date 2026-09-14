"""External secondary-provider probe for Block E. PAPER only."""
from __future__ import annotations
from datetime import datetime, timezone
import radar_block_e_market_data_v2 as e

REAL_TRADING=False


def _probe_one(name, fn, now):
    try:
        q=fn(); gate=e.market_data_gate(q,now=now)
        ok=q.provider_status=='OK' and q.price>0 and bool(q.market_timestamp)
        if name.startswith('stooq_'):
            ok=ok and q.source_kind=='FALLBACK_DAILY' and gate['paper_execution_eligible'] is False
        return ok, {'status':'PASS' if ok else 'FAILED','quote':q.dict(),'gate':gate}
    except Exception as exc:
        return False, {'status':'FAILED','error_class':e.classify_provider_exception(exc),'error':str(exc)[:300]}


def external_fallback_probe(symbol='MSFT'):
    now=datetime.now(timezone.utc)
    checks={}; details={}

    ok,detail=_probe_one('yahoo_query2',lambda:e.yahoo_chart_quote(symbol,'query2.finance.yahoo.com',now=now),now)
    checks['yahoo_query2']=ok; details['yahoo_query2']=detail

    stooq_ok=False; stooq_attempts={}
    for host,label in (('stooq.com','stooq_daily_com'),('stooq.pl','stooq_daily_pl')):
        ok,detail=_probe_one(label,lambda host=host:e.stooq_daily_mark(symbol,host,now=now),now)
        stooq_attempts[label]=detail
        if ok:
            stooq_ok=True
            break
    checks['stooq_daily_any']=stooq_ok
    details['stooq_daily_any']={'status':'PASS' if stooq_ok else 'UNAVAILABLE','attempts':stooq_attempts}

    # E1 requires a verified working fallback path. Yahoo query2 satisfies that requirement.
    # Stooq availability is additional diversity evidence and is reported truthfully rather than
    # being allowed to block the complete market-data gate.
    status='PASS' if checks['yahoo_query2'] else 'FAILED'
    return {
        'status':status,
        'checks':checks,'details':details,
        'verified_intraday_fallback':'Yahoo query2' if checks['yahoo_query2'] else None,
        'distinct_vendor_fallback_verified':stooq_ok,
        'stooq_policy':'DAILY_ANALYTICAL_FALLBACK_NOT_EXECUTABLE',
        'broker_connected':False,'live_execution_allowed':False,'real_trading':False,
    }
