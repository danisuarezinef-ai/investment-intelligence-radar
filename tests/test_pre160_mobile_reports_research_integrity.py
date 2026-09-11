import math

import radar_mobile_contract_v2 as mobile
import radar_reports_v1 as reports
import radar_learning_journal_v1 as journal
import radar_strategy_research_v1 as research
import radar_pre160_integrity_v1 as integ
import radar_multiwindow_ranking_v1 as windows


def test_mobile_contract_surfaces_champion_challenger_and_no_trading():
    league={'champion_key':'champion','leaderboard':[{'competitor_key':'champion','display_name':'Champion','current_equity':1100,'v_score':280,'v_confidence':.8,'max_drawdown_pct':-3,'league_role':'CHAMPION'},
          {'competitor_key':'a','display_name':'A','current_equity':1150,'v_score':295,'max_drawdown_pct':-4,'league_role':'CHALLENGER 1'}],
          'best_promotion_watch':{'competitor_key':'a','display_name':'A','readiness':84,'eta_text':'~4–6 jornadas'}}
    out=mobile.mobile_summary(league=league,simulator={'completed_cycles':10,'generation':2},data_quality={'score':90,'status':'GOOD'},cloud={'status':'ACTIVE'})
    assert out['champion']['v']==280
    assert out['top_challenger']['readiness']==84
    assert out['real_trading'] is False
    assert any(x['code']=='CHALLENGER_NEAR_PROMOTION' for x in out['alerts'])


def test_daily_and_weekly_reports_remain_paper_only():
    daily=reports.daily_report({'champion_key':'champion','leaderboard':[{'competitor_key':'champion','display_name':'Champion','current_equity':1000,'v_score':200}]})
    weekly=reports.weekly_report([{'day':'2026-01-01','ranking':[{'key':'champion','equity':1000,'v':200}]},{'day':'2026-01-07','ranking':[{'key':'champion','equity':1020,'v':210}]}])
    assert daily['real_trading'] is False
    assert weekly['strategies'][0]['equity_change_pct']>1.9


def test_learning_journal_can_invalidate_false_learning():
    lesson=journal.lesson_candidate(subject='x',claim='works',regime='RISK_ON',min_future_tests=3)
    invalid=journal.update_lesson(lesson,[False,False,True,False])
    risk=journal.false_learning_check(lesson,{'RISK_ON':8,'RISK_OFF':-3,'NEUTRAL':-1})
    assert invalid['status']=='INVALIDATED'
    assert risk['false_learning_risk']=='HIGH'


def test_challenger_factory_is_bounded_and_research_only():
    budget=research.experiment_budget(total_capacity=12,active=1,experimental_share=.25)
    muts=research.challenger_mutations({'risk_multiplier':1.0},slots=budget['new_slots'])
    assert len(muts)<=budget['new_slots']
    assert all(x['research_only'] and x['real_trading'] is False for x in muts)


def test_ensemble_caps_concentration_and_cannot_trade():
    out=research.ensemble_proposal([{'competitor_key':'a','v_score':350,'stability_score':90,'v_confidence':.9},{'competitor_key':'b','v_score':300,'stability_score':80,'v_confidence':.8},{'competitor_key':'c','v_score':280,'stability_score':75,'v_confidence':.8}],max_weight=.5)
    assert abs(sum(out['weights'].values())-1)<1e-9
    assert max(out['weights'].values())<=.500001
    assert out['can_trade'] is False


def test_abstention_is_first_class_when_quality_is_bad():
    out=research.abstention_gate([{'symbol':'X','score':10,'confidence':.9}],data_quality_score=40,calibration_status='PASS')
    assert out['decision']=='ABSTAIN'
    assert 'DATA_QUALITY' in out['blockers']


def test_paper_integrity_and_lookahead_fail_closed():
    bad=integ.paper_account_integrity({'cash':50,'invested':40,'total':100,'positions':[]})
    audit=integ.forward_timestamp_audit([{'created_at':'2026-01-01T00:00:00Z','data_cutoff':'2026-01-02T00:00:00Z','known_at_boundary':'2026-01-01T00:00:00Z','target_date':'2026-01-03T00:00:00Z','evaluated_at':'2026-01-04T00:00:00Z','backfilled':False}])
    assert bad['status']=='BLOCKED'
    assert audit['pass'] is False


def test_multiwindow_and_ranking_do_not_change_roles():
    series=[{'date':'2026-01-01T00:00:00Z','equity':1000},{'date':'2026-01-08T00:00:00Z','equity':1050},{'date':'2026-02-01T00:00:00Z','equity':1100}]
    perf=windows.multiwindow_performance(series)
    ranked=windows.multidimensional_ranking([{'competitor_key':'a','v_score':300},{'competitor_key':'b','v_score':250}],mode='v')
    assert math.isclose(perf['since_inception']['change_pct'],10,abs_tol=1e-9)
    assert ranked['ranking'][0]['competitor_key']=='a'
    assert ranked['changes_role'] is False
