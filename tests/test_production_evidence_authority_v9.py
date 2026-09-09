import io
import json

import cloud_service_v3 as cloud
import radar_core
import radar_fundamentals_point_in_time_v1 as fundamentals
import radar_market_runtime_v2 as market
import radar_operational_pipeline_v1 as operational
import radar_paper_authority_v1 as authority


def _db(tmp_path,monkeypatch):
    path=str(tmp_path/'radar.db');monkeypatch.setattr(radar_core,'DB',path);radar_core.init_db();return path


def test_provider_circuit_breaker_uses_observed_failures(tmp_path,monkeypatch):
    _db(tmp_path,monkeypatch)
    for _ in range(3):market._record('P1','MSFT','quote',False,5.0,'boom')
    assert market._circuit_open('P1') is True
    t=market.provider_telemetry(24)
    p=next(x for x in t['providers'] if x['name']=='P1')
    assert p['calls']==3 and p['failures']==3 and p['circuit_open'] is True
    assert t['provider_attempt_telemetry']=='LIVE_OBSERVED_ATTEMPTS'
    assert t['real_trading'] is False


def test_provider_success_resets_consecutive_failures(tmp_path,monkeypatch):
    _db(tmp_path,monkeypatch)
    market._record('P2','MSFT','quote',False,1.0,'x');market._record('P2','MSFT','quote',True,1.0)
    p=next(x for x in market.provider_telemetry(24)['providers'] if x['name']=='P2')
    assert p['consecutive_failures']==0 and p['calls']==2 and p['failures']==1


def test_fundamental_payload_never_invents_missing_values():
    payload=fundamentals._build_payload('MSFT',{'facts':{}})
    assert payload['revenue_growth'] is None and payload['operating_margin'] is None
    assert payload['free_cash_flow'] is None and payload['net_debt'] is None
    assert payload['real_trading'] is False


def test_fundamental_coverage_is_explicit_for_unsupported_assets(tmp_path,monkeypatch):
    _db(tmp_path,monkeypatch);out=fundamentals.fundamental_coverage()
    assert out['assets_expected']==len(radar_core.ASSETS)
    assert out['fundamentals_observed']==0
    assert out['valuation_multiple']=='NOT_YET_DERIVED_WITH_VERIFIED_MARKET_CAP'


def test_operational_valuation_uses_only_persisted_fundamentals(monkeypatch):
    monkeypatch.setattr(operational,'latest_fundamental',lambda symbol:{'known_at':'2026-09-01','revenue_growth':.1,'operating_margin':.2,'free_cash_flow':10.0,'net_debt':2.0,'shares_outstanding':5.0,'revenue':100.0,'source':'SEC'} if symbol=='MSFT' else None)
    ev=operational._valuation_evidence('MSFT',{'price':20.0,'ts':'2026-09-09T00:00:00+00:00'})
    assert ev['valuation_multiple']==1.0
    assert ev['valuation_multiple_kind']=='PRICE_TO_SALES_FROM_OBSERVED_PRICE_AND_FILED_SHARES'
    missing=operational._valuation_evidence('NVDA',{'price':20.0,'ts':'2026-09-09T00:00:00+00:00'})
    assert missing['revenue_growth'] is None and missing['valuation_multiple'] is None


def test_paper_authority_holds_when_optimizer_not_ready(monkeypatch):
    monkeypatch.setattr(authority,'paper_status',lambda:{'configured':True,'enabled':True,'cash':500.0,'total':1000.0,'positions':[{'symbol':'MSFT'}]})
    monkeypatch.setattr(authority,'operational_pipeline',lambda:{'optimizer':{'status':'HOLD_CASH','allocations':[]}})
    out=authority.paper_authority_step()
    assert out['status']=='HOLD_EXISTING_NO_NEW_RISK'
    assert out['legacy_momentum_fallback'] is False
    assert out['allocations']==[] and out['real_trading'] is False


def test_cloud_exposes_new_read_only_evidence_routes(monkeypatch):
    monkeypatch.setattr(cloud,'provider_telemetry',lambda hours:{'provider_attempt_telemetry':'LIVE_OBSERVED_ATTEMPTS','real_trading':False})
    monkeypatch.setattr(cloud,'fundamental_coverage',lambda:{'fundamentals_observed':0,'real_trading':False})
    for path,key in [('/provider-telemetry-v1','provider_attempt_telemetry'),('/fundamentals-v1','fundamentals_observed')]:
        h=cloud.ValidationV3Handler.__new__(cloud.ValidationV3Handler);h.path=path;h.headers={};h.rfile=io.BytesIO(b'');sent=[];h._send=lambda code,body:sent.append((code,body));h.do_GET();assert sent[0][0]==200 and key in sent[0][1]


def test_windows_sync_consumes_priority_pipeline_market_and_heartbeat():
    src=open('radar_pc_sync_hook.py',encoding='utf-8').read()
    assert "_get_optional('/priority-v1')" in src
    assert "_get_optional('/operational-pipeline-v1')" in src
    assert "_get_optional('/market-telemetry-v1')" in src
    assert "_post_path('/node-heartbeat'" in src
    assert "REAL TRADING OFF" in src


def test_worker_uses_evidence_authority_not_legacy_paper_step():
    src=open('run_worker.py',encoding='utf-8').read()
    assert 'from radar_market_runtime_v2 import collect_market' in src
    assert 'from radar_paper_authority_v1 import paper_authority_step' in src
    assert 'paper_step()' not in src and 'paper_step(force=True)' not in src
    assert 'collect_fundamentals()' in src


def test_forward_engine_is_prospective_and_cost_benchmark_explicit():
    src=open('radar_forward_engine.py',encoding='utf-8').read()
    assert "PAPER_ROUND_TRIP_COST=0.001" in src
    assert "BENCHMARK_NAME='RADAR_EQUAL_WEIGHT_OBSERVED_UNIVERSE'" in src
    assert "where outcome is null and target_date<=?" in src
    assert "'backfilled':False" in src
    assert 'REAL_TRADING=False' in src
