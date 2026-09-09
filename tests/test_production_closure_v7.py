import io

import cloud_service_v3 as cloud


def _handler(path):
    h=cloud.ValidationV3Handler.__new__(cloud.ValidationV3Handler)
    h.path=path; h.headers={}; h.rfile=io.BytesIO(b'')
    sent=[]; h._send=lambda code,body:sent.append((code,body))
    return h,sent


def test_priority_endpoint_is_read_only_and_exposes_wiring(monkeypatch):
    monkeypatch.setattr(cloud,'priority_runtime_live',lambda:{'wiring':{'priority_runtime':'LIVE'},'can_trade':False,'real_trading':False})
    h,sent=_handler('/priority-v1'); h.do_GET()
    assert sent[0][0]==200
    assert sent[0][1]['wiring']['priority_runtime']=='LIVE'
    assert sent[0][1]['can_trade'] is False and sent[0][1]['real_trading'] is False


def test_priority_live_marks_runtime_modules_explicitly(monkeypatch):
    monkeypatch.setattr(cloud,'validation_runtime_v3',lambda:{'paper_gate_evidence':{}})
    monkeypatch.setattr(cloud,'ops_health',lambda validation:{'freshness':{},'shadow_portfolio':{}})
    monkeypatch.setattr(cloud,'operational_pipeline',lambda:{'forward_records':[],'universe':{'screened':[]},'real_trading':False})
    out=cloud.priority_runtime_live()
    assert out['wiring']['priority_runtime']=='LIVE'
    assert out['wiring']['global_universe_v3']=='LIVE_READ_ONLY_OBSERVED_STATE'
    assert out['wiring']['valuation_engine_v1']=='LIVE_FAIL_CLOSED_MISSING_FUNDAMENTALS'
    assert out['wiring']['portfolio_optimizer_v3']=='LIVE_FAIL_CLOSED_EVIDENCE_GATED'
    assert out['wiring']['priority_forward_records'].startswith('LIVE_MATURED_LEDGER_ONLY')
    assert out['wiring']['generic_forward_autonomy_v1']=='VERIFIED_CODE_ONLY'
    assert out['strategy_performance_verified'] is False
    assert out['can_trade'] is False and out['real_trading'] is False


def test_windows_build_enforces_visible_radar_identity_without_renaming_executable():
    build=open('build_windows.ps1',encoding='utf-8').read()
    installer=open('installer/Radar.iss',encoding='utf-8').read()
    assert "root.title('Radar de Inversión')" in build
    assert "text='Radar de Inversión'" in build
    assert "'Radar de Inversión.lnk'" in build
    assert '--name InvestmentIntelligenceRadar' in build
    assert '#define MyAppName "Radar de Inversión"' in installer
    assert '#define MyAppExeName "InvestmentIntelligenceRadar.exe"' in installer
    assert 'OutputBaseFilename=Radar_de_Inversion_Setup' in installer
