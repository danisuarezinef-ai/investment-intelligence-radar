"""Controlled PAPER-only runtime disaster probes.

These probes execute inside the production container but cannot place orders or mutate
portfolio state. The duplicate-delivery probe runs inside an explicit SQLite transaction
that is always rolled back. Results are observation evidence only.
"""
from __future__ import annotations

from datetime import datetime, timezone

from radar_core import con
from radar_decision_provenance_v1 import capture_trade_envelope
from radar_simulator_hardening_v1 import safe_paper_fill

REAL_TRADING=False


def _market_failure_probe():
    now=datetime.now(timezone.utc)
    order={'side':'BUY','quantity':1.0,'symbol':'PROBE'}
    market={'symbol':'PROBE','source':'CONTROLLED_FAULT_INJECTION','observed_at':now.isoformat(),
            'missing_kind':'PROVIDER_FAILURE','mid_price':None,'available_volume':1000.0,
            'market_open':True,'snapshot_hash':'controlled-provider-failure'}
    out=safe_paper_fill(order,market,now=now)
    passed=(out.get('status')=='REJECTED' and float(out.get('filled_quantity') or 0)==0.0 and
            out.get('can_submit_order') is False and out.get('broker_connected') is False and
            out.get('real_trading') is False and (out.get('market_gate') or {}).get('status')=='FAIL')
    return {'scenario':'market_data_outage','result':'FAIL_CLOSED' if passed else 'INVALID',
            'passed':passed,'status':out.get('status'),'reason':out.get('reason'),
            'blockers':(out.get('market_gate') or {}).get('blockers') or [],
            'filled_quantity':out.get('filled_quantity'),'can_submit_order':out.get('can_submit_order'),
            'broker_connected':out.get('broker_connected'),'fault_injection':'CONTROLLED_PROVIDER_FAILURE',
            'real_trading':False}


def _corrupt_response_probe():
    now=datetime.now(timezone.utc)
    order={'side':'BUY','quantity':1.0,'symbol':'PROBE'}
    market={'symbol':'PROBE','source':'CONTROLLED_FAULT_INJECTION','observed_at':now.isoformat(),
            'mid_price':'CORRUPT_NOT_NUMERIC','available_volume':1000.0,'market_open':True}
    out=safe_paper_fill(order,market,now=now)
    passed=(out.get('status')=='REJECTED' and float(out.get('filled_quantity') or 0)==0.0 and
            out.get('can_submit_order') is False and out.get('broker_connected') is False and
            out.get('real_trading') is False and (out.get('market_gate') or {}).get('status')=='FAIL')
    return {'scenario':'corrupt_response','result':'FAIL_CLOSED' if passed else 'INVALID',
            'passed':passed,'status':out.get('status'),'reason':out.get('reason'),
            'blockers':(out.get('market_gate') or {}).get('blockers') or [],
            'filled_quantity':out.get('filled_quantity'),'can_submit_order':out.get('can_submit_order'),
            'broker_connected':out.get('broker_connected'),'fault_injection':'CONTROLLED_CORRUPT_MARKET_PAYLOAD',
            'real_trading':False}


def _duplicate_delivery_probe():
    c=con();trade_id=-931400001;source_key='disaster_probe_duplicate_delivery_v1'
    try:
        c.execute('begin immediate')
        ts=datetime.now(timezone.utc).isoformat()
        kwargs=dict(source_key=source_key,trade_id=trade_id,trade_ts=ts,competitor_key='DISASTER_PROBE',
                    strategy_identity='DISASTER_PROBE_V1',strategy_config={'probe':True},symbol='MSFT',side='BUY',
                    cost_snapshot={'probe':True},decision_payload={'probe':'duplicate_delivery'})
        first=capture_trade_envelope(c,**kwargs)
        second=capture_trade_envelope(c,**kwargs)
        count=int(c.execute('select count(*) from paper_decision_envelopes_local where source_key=? and trade_id=?',(source_key,trade_id)).fetchone()[0])
        passed=bool(first.get('envelope_hash')) and first.get('envelope_hash')==second.get('envelope_hash') and count==1
        return {'scenario':'duplicate_delivery','result':'EXACT_RECOVERY' if passed else 'INVALID',
                'passed':passed,'logical_records':count,'hash_equal':first.get('envelope_hash')==second.get('envelope_hash'),
                'transaction_rolled_back':True,'portfolio_mutated':False,'real_trading':False}
    finally:
        try:c.rollback()
        finally:c.close()


def run_controlled_probes():
    probes=[]
    for fn in (_market_failure_probe,_corrupt_response_probe,_duplicate_delivery_probe):
        try:probes.append(fn())
        except Exception as exc:probes.append({'scenario':fn.__name__,'result':'INVALID','passed':False,'error':f'{type(exc).__name__}: {str(exc)[:500]}','real_trading':False})
    return {'status':'PASS' if all(x.get('passed') is True for x in probes) else 'FAIL',
            'probes':probes,'portfolio_mutation_allowed':False,'broker_connected':False,'real_trading':False}
