"""Observed-state operational pipeline.

Wires universe, point-in-time valuation, optimizer, paper/shadow and forward
evidence without creating synthetic fundamentals, benchmark returns or costs.
REAL_TRADING remains false.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from radar_core import ASSETS, con, opportunity_rankings, paper_status
from radar_global_universe_v3 import build_global_funnel
from radar_valuation_engine_v1 import valuation_card, REQUIRED as VALUATION_REQUIRED
from radar_portfolio_optimizer_v3 import optimize_capital
from radar_fundamentals_point_in_time_v1 import latest_fundamental, fundamental_coverage
from radar_market_runtime_v2 import provider_telemetry

REAL_TRADING = False


def _latest_market_rows() -> dict[str, dict[str, Any]]:
    c = con(); out: dict[str, dict[str, Any]] = {}
    for symbol in ASSETS:
        row = c.execute('select price,volume,source,ts from market_snapshots where symbol=? and source not like ? order by ts desc,id desc limit 1',(symbol, '%Historical%')).fetchone()
        if row: out[symbol] = {'price': row[0], 'volume': row[1], 'source': row[2], 'ts': row[3]}
    c.close(); return out


def _age_seconds(ts: Any) -> float | None:
    if not ts:return None
    try:
        dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        if dt.tzinfo is None:dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:return None


def market_telemetry() -> dict[str, Any]:
    latest = _latest_market_rows(); rows = []; source_counts: dict[str, int] = {}
    for symbol in ASSETS:
        item = latest.get(symbol)
        if not item:
            rows.append({'symbol': symbol, 'status': 'MISSING', 'price': None, 'source': None,'timestamp': None, 'age_seconds': None, 'fallback_observed': False});continue
        source = str(item.get('source') or ''); source_counts[source] = source_counts.get(source, 0) + 1
        age = _age_seconds(item.get('ts')); status = 'FRESH' if age is not None and age <= 900 else ('STALE' if age is not None else 'UNKNOWN')
        rows.append({'symbol': symbol, 'status': status, 'price': item.get('price'), 'source': source or None,'timestamp': item.get('ts'), 'age_seconds': age,'fallback_observed': source.startswith('Stooq')})
    attempts=provider_telemetry(24); observed=len(latest)
    return {'assets_expected':len(ASSETS),'assets_observed':observed,'coverage_complete':observed==len(ASSETS),'assets':rows,
            'observed_source_counts':source_counts,'configured_provider_chain':['Yahoo query1','Yahoo query2','Stooq.com','Stooq.pl','Stooq daily fallback'],
            'provider_attempt_telemetry':attempts.get('provider_attempt_telemetry'),'provider_health':attempts.get('providers'),
            'recent_provider_attempts':attempts.get('recent_attempts'),'circuit_breaker':attempts.get('circuit_breaker'),
            'failover_activation_verified':attempts.get('failover_activation_verified') or any(x['fallback_observed'] for x in rows),
            'can_trade':False,'real_trading':False}


def _ranking_rows() -> list[dict[str, Any]]:
    ranks = opportunity_rankings(16); latest = _latest_market_rows(); rows=[]
    for tier in ('bajo','intermedio','alto'):
        for r in ranks.get(tier,[]):
            symbol=r.get('symbol');market=latest.get(symbol,{})
            rows.append({**r,'price':market.get('price'),'liquidity_score':None,'data_quality':1.0 if market.get('price') is not None else 0.0,
                         'momentum_score':r.get('score'),'deep_evidence_ready':bool(latest_fundamental(symbol)),
                         'decision_evidence_complete':False})
    return rows


def _valuation_evidence(symbol: str, market: dict[str, Any]) -> dict[str, Any]:
    fundamental=latest_fundamental(symbol) or {}; price=market.get('price');shares=fundamental.get('shares_outstanding');revenue=fundamental.get('revenue')
    multiple=None
    try:
        if price is not None and shares is not None and revenue not in (None,0):multiple=float(price)*float(shares)/float(revenue)
    except Exception:multiple=None
    known=[x for x in (market.get('ts'),fundamental.get('known_at')) if x]
    return {'price':price,'revenue_growth':fundamental.get('revenue_growth'),'operating_margin':fundamental.get('operating_margin'),
            'free_cash_flow':fundamental.get('free_cash_flow'),'net_debt':fundamental.get('net_debt'),'valuation_multiple':multiple,
            'valuation_multiple_kind':'PRICE_TO_SALES_FROM_OBSERVED_PRICE_AND_FILED_SHARES' if multiple is not None else None,
            'known_at':max(known) if known else None,'fundamental_source':fundamental.get('source')}


def _portfolio_drawdown_pct() -> float | None:
    c=con();rows=c.execute('select total from portfolio_values order by id').fetchall();c.close();vals=[float(x[0]) for x in rows if x and isinstance(x[0],(int,float)) and float(x[0])>0]
    if not vals:return None
    peak=vals[0];worst=0.0
    for value in vals:peak=max(peak,value);worst=min(worst,value/peak-1.0)
    return worst


def matured_forward_records() -> list[dict[str, Any]]:
    c=con()
    try:rows=c.execute('select id,asset,created_at,target_date,payload,outcome,evaluated_at from prediction_ledger where outcome is not null order by id').fetchall()
    except Exception:c.close();return []
    c.close();out=[]
    for row in rows:
        try:payload=json.loads(row[4]) if isinstance(row[4],str) else (row[4] or {})
        except Exception:payload={}
        try:outcome=json.loads(row[5]) if isinstance(row[5],str) else (row[5] or {})
        except Exception:outcome={}
        out.append({'ledger_id':row[0],'symbol':row[1],'created_at':row[2],'target_date':row[3],'evaluated_at':row[6],
                    'return_pct':outcome.get('return'),'net_return':outcome.get('net_return'),'excess_return':outcome.get('excess_return'),
                    'cost':outcome.get('cost'),'cost_model':outcome.get('cost_model'),'benchmark_return':outcome.get('benchmark_return'),
                    'benchmark_name':outcome.get('benchmark_name'),'decision_state':payload.get('decision_state'),'matured':True,
                    'backfilled':bool(outcome.get('backfilled',False))})
    return out


def operational_pipeline() -> dict[str, Any]:
    market=_latest_market_rows();ranked=_ranking_rows();funnel=build_global_funnel(ranked,screen_limit=500,deep_limit=40,decision_limit=12)
    valuations=[];optimizer_inputs=[]
    for candidate in funnel.get('screened',[]):
        symbol=candidate['symbol'];evidence=_valuation_evidence(symbol,market.get(symbol,{}));card=valuation_card(symbol,evidence);card['valuation_multiple_kind']=evidence.get('valuation_multiple_kind');card['fundamental_source']=evidence.get('fundamental_source');valuations.append(card)
        optimizer_inputs.append({'symbol':symbol,'evidence_complete':card['evidence_complete'],'expected_return':None,'risk_score':None,'valuation_score':card['valuation_score'],
                                 'prediction_evidence':'NOT_WIRED_TO_VERIFIED_FORWARD_EXPECTED_RETURN'})
    account=paper_status();drawdown=_portfolio_drawdown_pct()
    optimizer=optimize_capital(cash=float(account.get('cash') or 0),equity=float(account.get('total') or 0),opportunities=optimizer_inputs,drawdown_pct=drawdown) if account.get('configured') else {'status':'BLOCKED','reason':'PAPER_ACCOUNT_NOT_CONFIGURED','allocations':[],'can_trade':False,'real_trading':False}
    complete=sum(1 for x in valuations if x.get('evidence_complete') is True)
    return {'pipeline':['market_data','provider_health','point_in_time_fundamentals','global_universe_v3','valuation_engine_v1','prediction_ranking','portfolio_optimizer_v3','paper_shadow','forward_ledger','learning'],
            'universe':funnel,'valuations':valuations,'valuation_required_fields':list(VALUATION_REQUIRED),'valuation_complete_count':complete,
            'fundamental_coverage':fundamental_coverage(),'optimizer':optimizer,'forward_records':matured_forward_records(),'market_telemetry':market_telemetry(),
            'wiring_status':{'provider_attempt_telemetry':'LIVE_OBSERVED_ATTEMPTS','provider_circuit_breaker':'LIVE_PERSISTED_STATE',
                             'global_universe_v3':'LIVE_READ_ONLY_OBSERVED_STATE','fundamentals':'LIVE_POINT_IN_TIME_SEC_SUPPORTED_ASSETS',
                             'valuation_engine_v1':'LIVE_FAIL_CLOSED','portfolio_optimizer_v3':'LIVE_FAIL_CLOSED_MISSING_VERIFIED_EXPECTED_RETURN',
                             'forward_evidence_records':'LIVE_MATURED_LEDGER_ONLY'},'can_trade':False,'real_trading':False}
