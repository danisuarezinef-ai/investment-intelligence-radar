"""External secondary-provider probe for Block E. PAPER only."""
from __future__ import annotations
from datetime import datetime, timezone
import radar_block_e_market_data_v1 as e

REAL_TRADING=False


def external_fallback_probe(symbol='MSFT'):
    now=datetime.now(timezone.utc)
    checks={}
    details={}
    probes=(
        ('yahoo_query2', lambda: e.yahoo_chart_quote(symbol,'query2.finance.yahoo.com',now=now)),
        ('stooq_com', lambda: e.stooq_quote(symbol,'stooq.com',now=now)),
    )
    for name,fn in probes:
        try:
            q=fn(); gate=e.market_data_gate(q,now=now)
            ok=q.provider_status=='OK' and q.price>0 and bool(q.market_timestamp)
            checks[name]=ok
            details[name]={'status':'PASS' if ok else 'FAILED','quote':q.dict(),'gate':gate}
        except Exception as exc:
            checks[name]=False
            details[name]={'status':'FAILED','error_class':e.classify_provider_exception(exc),'error':str(exc)[:300]}
    return {
        'status':'PASS' if all(checks.values()) else 'PARTIAL',
        'checks':checks,'details':details,
        'secondary_sources_verified':sum(1 for x in checks.values() if x),
        'required_secondary_sources':len(checks),
        'broker_connected':False,'live_execution_allowed':False,'real_trading':False,
    }
