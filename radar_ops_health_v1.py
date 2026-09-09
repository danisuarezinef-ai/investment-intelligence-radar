"""Read-only operational health and freshness snapshot. No execution capability."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from radar_core import ASSETS, STATUS, con, init_db
from radar_intelligence import sync_nodes
from radar_shadow_portfolio_v2 import shadow_portfolio_v2_status
from radar_market_runtime_v2 import provider_telemetry

REAL_TRADING = False
CLOUD_VERSION = 'v3'
FRESHNESS_POLICY = {
    'market_data': {'healthy_seconds': 900, 'failed_seconds': 7200},
    'events': {'healthy_seconds': 7200, 'failed_seconds': 86400},
    'predictions': {'healthy_seconds': 7200, 'failed_seconds': 86400},
    'cloud_sync': {'healthy_seconds': 180, 'failed_seconds': 1800},
    'forward_outcomes': {'healthy_seconds': 172800, 'failed_seconds': 1209600},
}
PROVIDER_POLICY = [
    {'name': 'Yahoo query1', 'priority': 1, 'timeout_seconds': 15, 'fallback': 'Yahoo query2'},
    {'name': 'Yahoo query2', 'priority': 2, 'timeout_seconds': 15, 'fallback': 'Stooq.com'},
    {'name': 'Stooq.com', 'priority': 3, 'timeout_seconds': 15, 'fallback': 'Stooq.pl'},
    {'name': 'Stooq.pl', 'priority': 4, 'timeout_seconds': 15, 'fallback': 'Stooq.com daily'},
    {'name': 'Stooq.com daily', 'priority': 5, 'timeout_seconds': 20, 'fallback': 'Stooq.pl daily'},
    {'name': 'Stooq.pl daily', 'priority': 6, 'timeout_seconds': 20, 'fallback': None},
]


def _dt(value):
    if not value:return None
    try:return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc)
    except (TypeError, ValueError):return None


def freshness_state(timestamp, category, now_at=None):
    policy=FRESHNESS_POLICY[category];current=_dt(now_at) or datetime.now(timezone.utc);observed=_dt(timestamp)
    if observed is None:return {'status':'INSUFFICIENT_DATA','timestamp':timestamp,'age_seconds':None,'policy':policy,'policy_basis':'POLICY DEFAULT / NOT EMPIRICALLY VALIDATED'}
    age=max(0.0,(current-observed).total_seconds());status='HEALTHY' if age<=policy['healthy_seconds'] else ('DEGRADED' if age<=policy['failed_seconds'] else 'FAILED')
    return {'status':status,'timestamp':timestamp,'age_seconds':age,'policy':policy,'policy_basis':'POLICY DEFAULT / NOT EMPIRICALLY VALIDATED'}


def _status_file():
    try:
        with open(STATUS,'r',encoding='utf-8') as handle:value=json.load(handle);return value if isinstance(value,dict) else {}
    except Exception:return {}


def _asset_coverage(recent_errors=None):
    errors=recent_errors or [];init_db();db=con();rows=[]
    for symbol in ASSETS:
        row=db.execute('select price,source,ts from market_snapshots where symbol=? order by ts desc,id desc limit 1',(symbol,)).fetchone();fresh=freshness_state(row[2] if row else None,'market_data');symbol_error=next((item for item in errors if str(item).startswith(symbol+':')),None)
        rows.append({'symbol':symbol,'has_price':bool(row),'price':row[0] if row else None,'source':row[1] if row else None,'timestamp':row[2] if row else None,'freshness':fresh['status'],'error':symbol_error or (None if row else 'NO_PRICE')})
    db.close();return {'configured':len(ASSETS),'with_price':sum(1 for x in rows if x['has_price']),'fresh':sum(1 for x in rows if x['freshness']=='HEALTHY'),'assets':rows}


def ops_health(validation=None):
    status=_status_file();init_db();db=con();latest_market=db.execute('select max(ts) from market_snapshots').fetchone()[0];latest_event=db.execute('select max(ts) from information_events').fetchone()[0]
    try:latest_prediction=db.execute('select max(created_at) from prediction_ledger').fetchone()[0]
    except Exception:latest_prediction=None
    try:latest_outcome=db.execute('select max(evaluated_at) from prediction_ledger where evaluated_at is not null').fetchone()[0]
    except Exception:latest_outcome=None
    db.close()
    freshness={'market_data':freshness_state(latest_market,'market_data'),'events':freshness_state(latest_event,'events'),'predictions':freshness_state(latest_prediction,'predictions'),'cloud_sync':freshness_state(status.get('supabase_synced_at'),'cloud_sync'),'forward_outcomes':freshness_state(latest_outcome,'forward_outcomes')}
    states=[x['status'] for x in freshness.values()];overall='FAILED' if 'FAILED' in states else ('DEGRADED' if 'DEGRADED' in states else ('INSUFFICIENT_DATA' if 'INSUFFICIENT_DATA' in states else 'HEALTHY'))
    recent_errors=status.get('last_market_errors') or [];live=provider_telemetry(24);observed={x['name']:x for x in live.get('providers',[])};providers=[]
    for configured in PROVIDER_POLICY:
        row=observed.get(configured['name']) or {};calls=int(row.get('calls') or 0);failures=int(row.get('failures') or 0)
        state='NOT_VERIFIED' if calls==0 else ('OPEN_CIRCUIT' if row.get('circuit_open') else ('DEGRADED' if row.get('error_rate') is not None and row.get('error_rate')>.35 else 'HEALTHY'))
        providers.append({**configured,'status':state,'calls':calls,'failures':failures,'error_rate':row.get('error_rate'),'avg_latency_ms':row.get('avg_latency_ms'),'selected':row.get('selected',0),'recent_success':row.get('last_success_at'),'recent_failure':row.get('last_failure_at'),'consecutive_failures':row.get('consecutive_failures',0),'rate_limit':'NOT_VERIFIED','circuit_breaker':'OPEN' if row.get('circuit_open') else ('CLOSED' if calls else 'NOT_VERIFIED'),'circuit_open_until':row.get('circuit_open_until')})
    active=[x['name'] for x in providers if x['circuit_breaker']=='OPEN'];shadow=shadow_portfolio_v2_status();positions=shadow.get('positions') or []
    return {'status':overall,'service':'Radar de Inversión Cloud','cloud_version':CLOUD_VERSION,'app_version':os.environ.get('RADAR_APP_VERSION'),'deployed_sha':os.environ.get('RAILWAY_GIT_COMMIT_SHA') or os.environ.get('GIT_COMMIT_SHA'),'deployment_id':os.environ.get('RAILWAY_DEPLOYMENT_ID'),'started_at':status.get('started_at'),'uptime':freshness_state(status.get('started_at'),'forward_outcomes')['age_seconds'],'last_cycle':status.get('heartbeat'),'last_market_cycle':latest_market,'last_prediction':latest_prediction,'last_decision':status.get('learning_last_full'),'last_shadow_allocation':positions[0].get('created_at') if positions else None,'last_matured_outcome':latest_outcome,'last_supabase_sync':status.get('supabase_synced_at'),'freshness':freshness,'asset_coverage':_asset_coverage(recent_errors),'providers':providers,'provider_failures':recent_errors,'circuit_breakers':{'status':'LIVE_PERSISTED_STATE','active':active,'active_count':len(active),'failover_activation_verified':live.get('failover_activation_verified',False)},'nodes':sync_nodes(100),'shadow_portfolio':shadow,'promotion_status':((validation or {}).get('shadow_to_paper_governance_v2') or {}).get('gate'),'validation_status':'AVAILABLE' if validation else 'INSUFFICIENT_DATA','secrets_exposed':False,'can_trade':False,'real_trading':False}
