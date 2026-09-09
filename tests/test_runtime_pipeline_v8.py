import json

import cloud_service_v3
import radar_operational_pipeline_v1 as op
from radar_provider_resilience_v1 import failover_order


def test_market_telemetry_reports_all_assets_and_observed_fallback(monkeypatch):
    sample={s:{'price':100.0,'volume':1.0,'source':'Yahoo Finance','ts':'2999-01-01T00:00:00+00:00'} for s in op.ASSETS}
    first=next(iter(sample));sample[first]['source']='Stooq Quote'
    monkeypatch.setattr(op,'_latest_market_rows',lambda:sample)
    monkeypatch.setattr(op,'provider_telemetry',lambda hours:{'provider_attempt_telemetry':'LIVE_OBSERVED_ATTEMPTS','providers':[],'recent_attempts':[],'circuit_breaker':'LIVE_PERSISTED_STATE','failover_activation_verified':False})
    result=op.market_telemetry()
    assert result['assets_expected']==16 and result['assets_observed']==16
    assert result['coverage_complete'] is True
    assert result['failover_activation_verified'] is True
    assert result['provider_attempt_telemetry']=='LIVE_OBSERVED_ATTEMPTS'
    assert result['circuit_breaker']=='LIVE_PERSISTED_STATE'
    assert result['real_trading'] is False


def test_matured_forward_records_preserve_missing_cost_and_benchmark(monkeypatch):
    class C:
        def execute(self,*args):return self
        def fetchall(self):return [(1,'MSFT','2026-09-09T00:00:00+00:00','2026-09-10T00:00:00+00:00',json.dumps({'decision_state':'WAIT'}),json.dumps({'return':0.01}),'2026-09-10T00:01:00+00:00')]
        def close(self):pass
    monkeypatch.setattr(op,'con',lambda:C());rows=op.matured_forward_records()
    assert rows[0]['return_pct']==0.01
    assert rows[0]['net_return'] is None and rows[0]['excess_return'] is None
    assert rows[0]['cost'] is None and rows[0]['benchmark_return'] is None


def test_operational_pipeline_wires_modules_but_fails_closed(monkeypatch):
    monkeypatch.setattr(op,'_latest_market_rows',lambda:{'MSFT':{'price':100.0,'source':'Yahoo Finance','ts':'2999-01-01T00:00:00+00:00'}})
    monkeypatch.setattr(op,'_ranking_rows',lambda:[{'symbol':'MSFT','score':1.0,'risk':'bajo','momentum_score':1.0,'liquidity_score':None,'data_quality':1.0,'deep_evidence_ready':False,'decision_evidence_complete':False}])
    monkeypatch.setattr(op,'paper_status',lambda:{'configured':True,'cash':1000.0,'total':1000.0,'invested':0.0})
    monkeypatch.setattr(op,'_portfolio_drawdown_pct',lambda:0.0)
    monkeypatch.setattr(op,'matured_forward_records',lambda:[])
    monkeypatch.setattr(op,'market_telemetry',lambda:{'assets_expected':16,'assets_observed':1,'real_trading':False})
    monkeypatch.setattr(op,'fundamental_coverage',lambda:{'fundamentals_observed':0,'assets':[],'real_trading':False})
    monkeypatch.setattr(op,'latest_fundamental',lambda symbol:None)
    result=op.operational_pipeline()
    assert result['wiring_status']['global_universe_v3']=='LIVE_READ_ONLY_OBSERVED_STATE'
    assert result['wiring_status']['valuation_engine_v1']=='LIVE_FAIL_CLOSED'
    assert result['wiring_status']['portfolio_optimizer_v3']=='LIVE_FAIL_CLOSED_MISSING_VERIFIED_EXPECTED_RETURN'
    assert result['valuation_complete_count']==0
    assert result['optimizer']['allocations']==[]
    assert result['real_trading'] is False


def test_priority_runtime_uses_matured_forward_records(monkeypatch):
    monkeypatch.setattr(cloud_service_v3,'validation_runtime_v3',lambda:{'paper_gate_evidence':{},'paper':{}})
    monkeypatch.setattr(cloud_service_v3,'ops_health',lambda _:{'freshness':{},'shadow_portfolio':{}})
    monkeypatch.setattr(cloud_service_v3,'operational_pipeline',lambda:{'forward_records':[{'matured':True,'net_return':None,'excess_return':None}],'universe':{'screened':[]},'real_trading':False})
    result=cloud_service_v3.priority_runtime_live()
    assert result['wiring']['priority_forward_records'].startswith('LIVE_MATURED_LEDGER_')
    assert result['strategy_performance_verified'] is False
    assert result['real_trading'] is False


def test_failover_policy_opens_broken_provider_and_prefers_healthy():
    result=failover_order([{'name':'Yahoo query1','calls':4,'failures':4,'consecutive_failures':4},{'name':'Stooq.com','calls':10,'failures':0,'consecutive_failures':0}])
    assert result['providers'][0]['name']=='Stooq.com'
    assert result['providers'][-1]['status']=='OPEN_CIRCUIT'
    assert 'Yahoo query1' not in result['request_order']
    assert result['real_trading'] is False
