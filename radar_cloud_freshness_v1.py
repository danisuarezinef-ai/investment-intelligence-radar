"""Cloud/data freshness SLA for Windows↔Cloud and evidence surfaces."""
from __future__ import annotations
from datetime import datetime, timezone

REAL_TRADING=False
DEFAULT_SLA_SECONDS={'pc_sync':180,'node_heartbeat':180,'market':300,'forward_ledger':900,'provider_telemetry':600}


def _dt(value):
    if not value:return None
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except Exception:return None


def freshness_snapshot(timestamps,now=None,sla_seconds=None):
    now=now or datetime.now(timezone.utc);sla={**DEFAULT_SLA_SECONDS,**(sla_seconds or {})};rows=[]
    for key,limit in sla.items():
        ts=_dt((timestamps or {}).get(key));age=None if ts is None else max(0.0,(now-ts).total_seconds())
        state='MISSING' if age is None else ('FRESH' if age<=float(limit) else 'STALE')
        rows.append({'surface':key,'timestamp':None if ts is None else ts.isoformat(),'age_seconds':age,'sla_seconds':float(limit),'state':state})
    blocking=[r for r in rows if r['surface'] in ('pc_sync','node_heartbeat','market') and r['state']!='FRESH']
    return {'status':'FRESH' if not blocking else 'DEGRADED','surfaces':rows,'blocking':blocking,'can_trade':False,'real_trading':False}
