import radar_paper_authority_v2 as pa
from radar_attribution_engine_v2 import attribute
from radar_degradation_watch_v2 import degradation_v2
from radar_dashboard_ui_contract_v1 import ui_contract
from radar_mobile_widget_contract_v1 import widget_payload


def test_paper_authority_is_gate_closed(monkeypatch):
    assert pa.execute_paper_allocations({},[],{})['status']=='BLOCKED_BY_PROMOTION_GATE'
    monkeypatch.setattr(pa,'record_fill',lambda **k:{'status':'PAPER_FILL_RECORDED','real_trading':False})
    g={'paper_execution_allowed':True}
    a=[{'symbol':'MSFT','amount':100,'prediction_evidence':'VERIFIED_FORWARD'}]
    x=pa.execute_paper_allocations(g,a,{'MSFT':100})
    assert x['status']=='PAPER_EXECUTED' and x['real_trading'] is False


def test_attribution_requires_cost_and_benchmark():
    assert attribute({'net_return':.01})['attributable'] is False
    x=attribute({'net_return':.01,'benchmark_return':.005,'excess_return':.004,'cost':.001,'backfilled':False},{'mom':1})
    assert x['attributable'] is True and x['real_trading'] is False


def test_degradation_hard_stops_new_capital():
    x=degradation_v2(market={'assets_expected':10,'assets_observed':5})
    assert x['status']=='DEGRADED' and x['new_capital_allowed'] is False


def test_dashboard_contract_has_balance_and_real_trading_off():
    x=ui_contract({'balance':{'equity':1000,'cash':500,'drawdown_pct':-.01},'evidence_state':'INSUFFICIENT_EVIDENCE'})
    assert x['primary_cards'][0]['id']=='equity' and x['banner']=='REAL TRADING OFF'


def test_widget_focuses_on_balance_and_warning():
    x=widget_payload({'balance':{'equity':1000,'cash':300,'drawdown_pct':-.08},'evidence_state':'MATURE','forward_evidence':{'predictions':50,'matured':5},'cloud_operational':True})
    assert x['balance']==1000 and x['alert_state']=='DRAWDOWN_WARNING' and x['display_mode']=='PAPER'
