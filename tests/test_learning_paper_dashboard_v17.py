import radar_learning_engine_v3 as le
import radar_paper_portfolio_v5 as pp


def test_learning_rejects_non_mature_or_non_cost_benchmark_records():
    rows=[{'immutable':True,'matured':True,'backfilled':False,'signals':{'x':1},'horizon':'1m','regime':'R','net_return':.01,'excess_return':.005,'cost_aware':False,'benchmark_aware':True}]
    x=le.learn_v3(rows,min_samples=1,min_forward_days=1)
    assert x['eligible_records']==0
    assert x['automatic_application'] is False


def test_learning_requires_time_and_sample_depth():
    rows=[{'immutable':True,'matured':True,'backfilled':False,'signals':{'x':1},'horizon':'1m','regime':'R','net_return':.01,'excess_return':.005,'cost_aware':True,'benchmark_aware':True,'target_date':'2026-09-01'} for _ in range(3)]
    x=le.learn_v3(rows,min_samples=3,min_forward_days=2)
    assert x['groups'][0]['status']=='INSUFFICIENT_EVIDENCE'


def test_paper_fill_rejects_backfill(monkeypatch):
    monkeypatch.setattr(pp,'ensure_account',lambda *a,**k:None)
    try:
        pp.record_fill(symbol='MSFT',side='BUY',quantity=1,price=100,backfilled=True)
        assert False
    except ValueError as e:
        assert 'backfill' in str(e)


def test_real_trading_false_contract():
    assert le.REAL_TRADING is False
    assert pp.REAL_TRADING is False
