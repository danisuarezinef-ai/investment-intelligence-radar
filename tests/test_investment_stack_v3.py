from radar_shadow_portfolio_v3 import new_shadow_account, rebalance_shadow, mark_shadow
from radar_attribution_v3 import attribute_trade_v3
from radar_learning_engine_v3 import learn_v3
from radar_model_competition_v3 import compete_models
from radar_multi_benchmark_v1 import compare_benchmarks
from radar_investment_stack_v3 import investment_stack_v3_snapshot


def test_shadow_v3_forbids_backfill_and_real_trading():
    a=new_shadow_account(1000,'2026-01-02T10:00:00Z')
    r=rebalance_shadow(a,{'MSFT':0.5},{'MSFT':{'price':100,'ts':'2026-01-02T09:00:00Z'}},'2026-01-01T10:00:00Z')
    assert r['applied'] is False and r['reason']=='backfill_forbidden' and r['real_trading'] is False


def test_shadow_v3_rebalance_and_mark():
    a=new_shadow_account(1000,'2026-01-01T00:00:00Z')
    r=rebalance_shadow(a,{'MSFT':0.5},{'MSFT':{'price':100,'ts':'2026-01-02T09:00:00Z'}},'2026-01-02T10:00:00Z',costs_bps=10)
    assert r['applied'] is True and r['fees']>0
    m=mark_shadow(a,{'MSFT':{'price':110,'ts':'2026-01-03T09:00:00Z'}},'2026-01-03T10:00:00Z')
    assert m['valid'] is True and m['equity']>0 and m['real_trading'] is False


def test_attribution_requires_benchmark_and_costs():
    assert attribute_trade_v3({'return_pct':5})['attributable'] is False
    a=attribute_trade_v3({'return_pct':5,'benchmark_return_pct':2,'costs_pct':0.5})
    assert a['net_return_pct']==4.5 and a['selection_excess_pct']==2.5


def test_learning_v3_uses_only_matured_immutable_nonbackfilled():
    good=[{'immutable':True,'matured':True,'backfilled':False,'return_pct':2,'signals':{'mom':1},'horizon':'30d','regime':'RISK_ON'} for _ in range(3)]
    bad=[{'immutable':True,'matured':False,'return_pct':9,'signals':{'mom':1},'horizon':'30d','regime':'RISK_ON'}]
    out=learn_v3(good+bad,min_samples=3)
    row=out['groups'][0]
    assert row['samples']==3 and row['status']=='LEARNED' and out['automatic_application'] is False


def test_model_competition_excludes_degraded_and_never_auto_applies():
    out=compete_models([
        {'model_id':'a','samples':40,'brier':0.18,'hit_rate':0.56,'excess_return_pct':2},
        {'model_id':'b','samples':40,'brier':0.40,'hit_rate':0.40,'excess_return_pct':-4},
    ])
    a=next(x for x in out['models'] if x['model_id']=='a'); b=next(x for x in out['models'] if x['model_id']=='b')
    assert a['recommended_weight']>0 and b['recommended_weight']==0 and out['automatic_application'] is False


def test_multi_benchmark_missing_is_not_zero():
    rows=[{'immutable':True,'matured':True,'backfilled':False,'net_return_pct':5,'benchmarks':{'global':3}}]
    out=compare_benchmarks(rows)
    global_row=next(x for x in out['benchmarks'] if x['benchmark']=='global')
    sector=next(x for x in out['benchmarks'] if x['benchmark']=='sector')
    assert global_row['mean_excess_pct']==2 and sector['mean_excess_pct'] is None


def test_stack_v3_never_trades():
    out=investment_stack_v3_snapshot([],[])
    assert out['can_trade'] is False and out['real_trading'] is False and out['automatic_application'] is False
