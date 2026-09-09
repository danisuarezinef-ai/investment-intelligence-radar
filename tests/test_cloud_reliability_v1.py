import io
import json
from datetime import datetime, timedelta, timezone

import cloud_service_v3 as cloud
import radar_core
import radar_intelligence
import radar_ops_health_v1 as ops
import radar_shadow_portfolio_v2 as shadow
import run_worker


def _handler(path, payload=b'', token='secret'):
    h=cloud.ValidationV3Handler.__new__(cloud.ValidationV3Handler); h.path=path
    h.headers={'Authorization':'Bearer '+token,'Content-Length':str(len(payload))}; h.rfile=io.BytesIO(payload)
    sent=[]; h._send=lambda code,body:sent.append((code,body)); return h,sent


def _db(tmp_path,monkeypatch):
    path=str(tmp_path/'radar.db'); monkeypatch.setattr(radar_core,'DB',path); monkeypatch.setattr(radar_intelligence,'DB',path,raising=False)
    monkeypatch.setattr(ops,'STATUS',str(tmp_path/'status.json')); radar_core.init_db(); radar_intelligence.init_intelligence_db()


def test_node_heartbeat_contract_auth_validation_and_persistence(tmp_path,monkeypatch):
    _db(tmp_path,monkeypatch); monkeypatch.setattr(run_worker,'CONTROL_TOKEN','secret')
    body=json.dumps({'node_id':'windows-1','node_type':'desktop','app_version':'1.5.5','capabilities':['desktop-ui']}).encode()
    h,sent=_handler('/node-heartbeat',body); h.do_POST(); assert sent[0][0]==200 and sent[0][1]['node']['node_id']=='windows-1'
    rows=radar_intelligence.sync_nodes(); assert rows[0]['node_id']=='windows-1' and rows[0]['last_seen']
    update=json.dumps({'node_id':'windows-1','node_type':'desktop','app_version':'1.5.6','detail':'updated'}).encode()
    h,sent=_handler('/node-heartbeat',update); h.do_POST(); rows=radar_intelligence.sync_nodes()
    assert sent[0][0]==200 and rows[0]['app_version']=='1.5.6' and rows[0]['detail']=='updated'
    h,sent=_handler('/node-heartbeat',body,token='wrong'); h.do_POST(); assert sent[0][0]==401
    h,sent=_handler('/node-heartbeat',b'{}'); h.do_POST(); assert sent[0][0]==400
    h,sent=_handler('/node-heartbeat',b'{'); h.do_POST(); assert sent[0][0]==400


def test_unknown_endpoint_remains_404(monkeypatch):
    monkeypatch.setattr(run_worker,'CONTROL_TOKEN','secret'); h,sent=_handler('/not-a-route',b'{}'); h.do_POST(); assert sent[0][0]==404


def test_freshness_uses_category_policies_and_missing_is_not_zero():
    now=datetime.now(timezone.utc); old=(now-timedelta(hours=3)).isoformat()
    assert ops.freshness_state(old,'market_data',now.isoformat())['status']=='FAILED'
    assert ops.freshness_state(old,'events',now.isoformat())['status']=='DEGRADED'
    missing=ops.freshness_state(None,'predictions',now.isoformat()); assert missing['status']=='INSUFFICIENT_DATA' and missing['age_seconds'] is None


def test_ops_health_is_read_only_and_fail_closed(tmp_path,monkeypatch):
    _db(tmp_path,monkeypatch); out=ops.ops_health()
    assert out['status'] in ('HEALTHY','DEGRADED','INSUFFICIENT_DATA','FAILED')
    assert out['asset_coverage']['configured']==len(radar_core.ASSETS)
    assert out['validation_status']=='INSUFFICIENT_DATA'
    assert len(out['providers'])==6
    assert all(item['circuit_breaker']=='NOT_VERIFIED' for item in out['providers'])
    assert out['circuit_breakers']['status']=='LIVE_PERSISTED_STATE'
    assert out['circuit_breakers']['active']==[]
    assert out['can_trade'] is False and out['real_trading'] is False


def test_ops_health_endpoint(monkeypatch):
    monkeypatch.setattr(cloud,'validation_runtime_v3',lambda:{'shadow_to_paper_governance_v2':{'gate':{'ready_for_paper_review':False}},'real_trading':False})
    monkeypatch.setattr(cloud,'ops_health',lambda validation:{'status':'INSUFFICIENT_DATA','deployed_sha':None,'can_trade':False,'real_trading':False})
    h,sent=_handler('/ops-health'); h.do_GET(); assert sent[0][0]==200 and sent[0][1]['real_trading'] is False


def test_runtime_missing_forward_coverage_is_explicit(monkeypatch):
    import radar_validation_runtime_v3 as runtime
    monkeypatch.setattr(runtime,'validation_runtime_snapshot',lambda:{'shadow':{},'forward':{},'historical_lab':{},'decision_lab_v5':{}})
    monkeypatch.setattr(runtime,'shadow_portfolio_v2_status',lambda:{'started':False,'decisions':0,'marks':0,'real_trading':False})
    out=runtime.validation_runtime_v3()
    assert out['paper_gate_evidence']['benchmark_coverage'] is None
    assert out['paper_gate_evidence']['cost_coverage'] is None
    assert out['paper_gate_evidence']['evidence_status']=='INSUFFICIENT_EVIDENCE'
    assert out['auto_promote'] is False and out['real_trading'] is False


def test_observability_does_not_backfill_shadow_decisions(tmp_path,monkeypatch):
    _db(tmp_path,monkeypatch)
    db=radar_core.con(); shadow.init_shadow_portfolio(db); before=db.execute('select count(*) from shadow_portfolio_decisions_v2').fetchone()[0]; db.close()
    ops.ops_health()
    db=radar_core.con(); after=db.execute('select count(*) from shadow_portfolio_decisions_v2').fetchone()[0]; db.close()
    assert before==after==0


def test_windows_cloud_route_and_identity_compatibility_contract():
    desktop=open('radar_desktop_v2.py',encoding='utf-8').read()
    cloud_source=open('cloud_service.py',encoding='utf-8').read()
    v3_source=open('cloud_service_v3.py',encoding='utf-8').read()
    installer=open('installer/Radar.iss',encoding='utf-8').read()
    updater=open('radar_updater_v2.py',encoding='utf-8').read()
    assert "cloud_get('/health')" in desktop and "cloud_get('/snapshot')" in desktop
    assert "cloud_post('/node-heartbeat'" in desktop
    assert "'/dashboard-v2'" in cloud_source and "path=='/pc-sync'" in cloud_source
    assert "path=='/validation-v3'" in v3_source and "path=='/ops-health'" in v3_source
    assert '#define MyAppName "Radar de Inversión"' in installer
    assert '#define MyAppExeName "InvestmentIntelligenceRadar.exe"' in installer
    assert 'OutputBaseFilename=Radar_de_Inversion_Setup' in installer
    assert 'RadarUpdate.zip' in updater
