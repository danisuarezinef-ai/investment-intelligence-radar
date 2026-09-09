"""Cloud/desktop contract audit model to consume Work reliability results safely."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
REAL_TRADING=False
REQUIRED_ENDPOINTS=('/health','/snapshot','/dashboard-v2','/notifications','/pc-sync','/node-heartbeat','/validation-v3','/ops-health')

def audit_contract(endpoint_status:dict[str,Any], freshness:dict[str,Any])->dict[str,Any]:
    endpoints={p: endpoint_status.get(p,'NOT_VERIFIED') for p in REQUIRED_ENDPOINTS}
    failed=[p for p,s in endpoints.items() if s not in (200,'200','VERIFIED')]
    domains={k:freshness.get(k,'NOT_VERIFIED') for k in ('market','events','predictions','cloud_sync','forward_outcomes')}
    return {'checked_at':datetime.now(timezone.utc).isoformat(),'endpoints':endpoints,'endpoint_failures':failed,
            'freshness':domains,'status':'HEALTHY' if not failed and all(v!='NOT_VERIFIED' for v in domains.values()) else 'DEGRADED_OR_UNVERIFIED',
            'source':'OBSERVED_INPUT_ONLY','can_trade':False,'real_trading':False}
