import json
import radar_expected_return_v1 as er
from radar_portfolio_optimizer_v3 import optimize_capital
from radar_champion_challenger_v1 import compete


class FakeDB:
    def __init__(self,rows):self.rows=rows
    def execute(self,sql,args=()):self.sql=sql;return self
    def fetchall(self):return self.rows
    def close(self):pass


def test_forward_calibration_reads_immutable_ledger_outcomes(monkeypatch):
    rows=[('MSFT',json.dumps({'net_return':0.02,'excess_return':0.015,'backfilled':False})),
          ('NVDA',json.dumps({'net_return':-0.01,'excess_return':-0.02,'backfilled':False}))]
    monkeypatch.setattr(er,'con',lambda:FakeDB(rows))
    x=er.forward_calibration(None,'1m')
    assert x['evidence_source']=='FORWARD_LEDGER'
    assert x['n']==2 and x['excess_n']==2
    assert round(x['mean_return_pct'],6)==0.5
    assert round(x['mean_excess_return_pct'],6)==-0.25


def test_optimizer_does_not_mix_return_and_unitless_risk_by_subtraction():
    x=optimize_capital(cash=1000,equity=1000,drawdown_pct=0.0,opportunities=[
        {'symbol':'MSFT','evidence_complete':True,'prediction_evidence':'VERIFIED_FORWARD','expected_return':0.02,'risk_score':0.40}
    ])
    assert x['status']=='READY'
    assert x['allocations'][0]['utility']>0


def test_optimizer_rejects_unverified_expected_return():
    x=optimize_capital(cash=1000,equity=1000,drawdown_pct=0.0,opportunities=[
        {'symbol':'MSFT','evidence_complete':True,'prediction_evidence':'INSUFFICIENT_FORWARD_EVIDENCE','expected_return':0.02,'risk_score':0.20}
    ])
    assert x['status']=='HOLD_CASH' and x['allocations']==[]


def test_champion_requires_mature_cost_and_benchmark_aware_forward_evidence():
    weak={'model_id':'a','forward_n':100,'forward_days':30,'mean_excess_return':0.03,'forward_only':True,'matured_only':True,'cost_aware':False,'benchmark_aware':True,'backfilled':False}
    assert compete([weak])['status']=='INSUFFICIENT_EVIDENCE'
    good={**weak,'cost_aware':True}
    assert compete([good])['status']=='READY'


def test_champion_never_enables_real_trading_or_auto_replacement():
    good={'model_id':'a','forward_n':100,'forward_days':30,'mean_excess_return':0.03,'forward_only':True,'matured_only':True,'cost_aware':True,'benchmark_aware':True,'backfilled':False}
    x=compete([good])
    assert x['automatic_replacement'] is False
    assert x['real_trading'] is False and x['can_trade'] is False
