from datetime import datetime, timedelta, timezone

import radar_simulator_hardening_v1 as h


def _now():
    return datetime.now(timezone.utc)


def _market(t):
    return {'symbol':'MSFT','source':'provider-x','observed_at':t.isoformat(),'mid_price':100.0,
            'available_volume':10000.0,'market_open':True,'snapshot_hash':'abc','missing_kind':None}


def test_exact_restore_requires_hash_identity_and_no_backfill():
    ok={'status':'RESTORED_EXACT_PAPER_ENGINE','verified':True,'remote_state_hash':'x','local_state_hash':'x',
        'backfill_used':False,'reconstructed':False,'can_trade':False,'real_trading':False}
    assert h.exact_restore_gate(ok)['status']=='PASS'
    bad=dict(ok, local_state_hash='y')
    assert h.exact_restore_gate(bad)['status']=='FAIL'
    assert 'hash_equal' in h.exact_restore_gate(bad)['blockers']


def test_continuity_requires_single_fresh_lease_and_session():
    t=_now()
    session={'session_id':'paper-1','real_trading':False}
    sim={'active':True,'last_cycle_at':t.isoformat(),'last_error':None,'real_trading':False}
    control={'duplicate_simulator_started':False}
    lease={'active_instances':1,'owner_id':'deployment-a','heartbeat_at':t.isoformat()}
    assert h.continuity_gate(session=session,simulator=sim,control=control,lease=lease,now=t.isoformat())['status']=='PASS'
    assert h.continuity_gate(session=session,simulator=sim,control=control,lease=dict(lease,active_instances=2),now=t.isoformat())['status']=='FAIL'


def test_market_snapshot_fails_closed_on_stale_provider_data():
    t=_now(); old=t-timedelta(minutes=10)
    g=h.market_snapshot_gate(_market(old),now=t.isoformat())
    assert g['status']=='FAIL' and 'fresh' in g['blockers']


def test_safe_paper_fill_blocks_closed_market_and_models_costs():
    t=_now(); market=_market(t)
    closed=dict(market,market_open=False)
    assert h.safe_paper_fill({'side':'BUY','quantity':10},closed,now=t.isoformat())['reason']=='market_closed'
    fill=h.safe_paper_fill({'side':'BUY','quantity':10},market,now=t.isoformat())
    assert fill['status']=='FILLED'
    assert fill['fees']>0 and fill['fill_price']>fill['mid_price']
    assert fill['can_submit_order'] is False and fill['real_trading'] is False


def test_temporal_isolation_rejects_future_knowledge_and_historical_maturity():
    t=_now(); later=t+timedelta(minutes=1)
    good={'decision_at':t.isoformat(),'evidence':[{'known_at':t.isoformat()}],
          'forward_maturity_source':'PROSPECTIVE_PAPER','automatic_promotion':False,'real_trading':False}
    assert h.temporal_isolation_gate(good)['status']=='PASS'
    bad=dict(good,evidence=[{'known_at':later.isoformat()}],forward_maturity_source='BACKTEST')
    g=h.temporal_isolation_gate(bad)
    assert g['status']=='FAIL'
    assert 'no_future_evidence' in g['blockers']
    assert 'historical_not_forward_maturity' in g['blockers']


def test_learning_closure_accepts_evaluated_trade_and_explicit_abstention():
    t=_now(); later=t+timedelta(days=1)
    trade={'episode_id':'e1','agent_id':'balanced','signal_family':'quality','regime':'risk_on','horizon':'1d',
           'action':'BUY','created_at':t.isoformat(),'evaluated_at':later.isoformat(),'outcome':{'return_pct':1.0},
           'lesson':'worked after costs','automatic_promotion':False,'real_trading':False}
    assert h.learning_closure_gate(trade)['status']=='PASS'
    abstain={'episode_id':'e2','agent_id':'balanced','reason':'confidence below threshold','regime':'risk_off','horizon':'1d',
             'action':'ABSTAIN_LOW_CONFIDENCE','created_at':t.isoformat(),'automatic_promotion':False,'real_trading':False}
    assert h.learning_closure_gate(abstain)['status']=='PASS'


def test_composite_gate_is_fail_closed_and_never_authorizes_live_execution():
    t=_now(); restore={'status':'RESTORED_EXACT_PAPER_ENGINE','verified':True,'remote_state_hash':'x','local_state_hash':'x',
        'backfill_used':False,'reconstructed':False,'can_trade':False,'real_trading':False}
    session={'session_id':'paper-1','real_trading':False}
    sim={'active':True,'last_cycle_at':t.isoformat(),'last_error':None,'real_trading':False}
    control={'duplicate_simulator_started':False}
    lease={'active_instances':1,'owner_id':'deployment-a','heartbeat_at':t.isoformat()}
    temporal={'decision_at':t.isoformat(),'evidence':[{'known_at':t.isoformat()}],
              'forward_maturity_source':'PROSPECTIVE_PAPER','automatic_promotion':False,'real_trading':False}
    learning={'episode_id':'e2','agent_id':'balanced','reason':'no edge','regime':'risk_off','horizon':'1d',
              'action':'HOLD','created_at':t.isoformat(),'automatic_promotion':False,'real_trading':False}
    gate=h.simulator_autonomous_gate(base_gate={'status':'SIMULATOR_READY'},restore=restore,session=session,
        simulator=sim,control=control,lease=lease,market=_market(t),temporal_probe=temporal,
        learning_probe=learning,now=t.isoformat())
    assert gate['status']=='PASS'
    assert gate['live_execution_allowed'] is False
    assert gate['automatic_promotion'] is False
    assert gate['automatic_release'] is False
    assert gate['setup_1_6_allowed'] is False
    assert gate['real_trading'] is False
