from datetime import datetime, timedelta, timezone

import radar_simulator_hardening_16_25_v1 as h

NOW = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)


def test_16_distributed_lease_requires_fresh_matching_session():
    lease={
        'lease_name':'autonomous-paper','owner_id':'railway-1','session_id':'s1','epoch':2,
        'heartbeat_at':(NOW-timedelta(seconds=20)).isoformat(),
        'expires_at':(NOW+timedelta(minutes=2)).isoformat(),'real_trading':False,
    }
    out=h.distributed_lease_gate(lease,expected_session_id='s1',now=NOW)
    assert out['status']=='PASS'
    bad=h.distributed_lease_gate({**lease,'session_id':'s2'},expected_session_id='s1',now=NOW)
    assert bad['status']=='FAIL'
    assert bad['live_execution_allowed'] is False


def test_17_end_to_end_gate_fails_closed_on_missing_component():
    names=['restore','continuity','lease','market_data','temporal_isolation','risk','abstention',
           'paper_execution','accounting','learning','persistence','maturity']
    gates={name:{'status':'PASS'} for name in names}
    gates['risk']['status']='PASS_PAPER_RISK'
    gates['accounting']['status']='RECONCILED'
    gates['maturity']['status']='VALID_FORWARD_CLOCK'
    gates['paper_execution']['status']='FILLED'
    gates['learning']['status']='LEARN_PAPER'
    assert h.end_to_end_runtime_gate(gates=gates)['status']=='PASS'
    gates.pop('market_data')
    out=h.end_to_end_runtime_gate(gates=gates)
    assert out['status']=='FAIL'
    assert out['paper_cycle_allowed'] is False


def test_18_watchdog_only_auto_recovers_exact_checkpoint_with_lease():
    runtime={
        'heartbeat_at':(NOW-timedelta(minutes=10)).isoformat(),
        'last_cycle_at':(NOW-timedelta(minutes=20)).isoformat(),
        'hung':True,'consecutive_errors':4,'max_consecutive_errors':3,
        'exact_checkpoint_available':True,'checkpoint_hash_verified':True,
        'distributed_lease_held':True,
    }
    out=h.watchdog_recovery_gate(runtime,now=NOW)
    assert out['status']=='AUTO_RECOVER_EXACT_PAPER'
    assert out['restart_allowed'] is True
    fail=h.watchdog_recovery_gate({**runtime,'checkpoint_hash_verified':False},now=NOW)
    assert fail['status']=='FAIL_CLOSED'
    assert fail['restart_allowed'] is False


def test_19_disaster_matrix_requires_all_scenarios_and_exact_or_safe_failure():
    scenarios=['process_kill','redeploy_mid_position','supabase_outage','market_data_outage',
               'corrupt_response','timeout','duplicate_delivery','duplicate_instance']
    rows=[]
    for s in scenarios:
        rows.append({'scenario':s,'result':'EXACT_RECOVERY','state_hash_equal':True,
                     'session_continuity':True,'real_trading':False})
    out=h.disaster_test_gate(rows)
    assert out['status']=='PASS'
    assert h.disaster_test_gate(rows[:-1])['status']=='FAIL'


def test_20_persistence_divergence_never_silent_overwrites():
    base={'state_hash':'x','session_id':'s','cycle':10,'cash':100,'equity':120,
          'positions_hash':'p','learning_hash':'l','observed_at':NOW.isoformat(),
          'backfilled':False,'real_trading':False}
    assert h.persistence_reconciliation_gate(base,dict(base))['status']=='RECONCILED'
    out=h.persistence_reconciliation_gate(base,{**base,'cycle':11})
    assert out['status']=='CRITICAL_PERSISTENCE_DIVERGENCE'
    assert out['silent_overwrite_allowed'] is False
    assert out['new_paper_risk_allowed'] is False


def test_21_decision_journal_rejects_future_evidence():
    entry={'decision_id':'d1','decision_at':NOW.isoformat(),'action':'BUY','confidence':0.7,
           'regime':'bull','horizon':'1d','agent_votes':[{'agent':'a','vote':'BUY'}],
           'risk':{'status':'PASS'},'causal_thesis':'earnings revision','reason':'consensus',
           'evidence':[{'known_at':(NOW-timedelta(minutes=1)).isoformat()}],
           'real_trading':False}
    assert h.decision_journal_gate(entry)['status']=='PASS'
    bad={**entry,'evidence':[{'known_at':(NOW+timedelta(seconds=1)).isoformat()}]}
    assert h.decision_journal_gate(bad)['status']=='FAIL'


def test_22_forward_horizons_do_not_use_unmatured_outcomes():
    decision={'decision_at':(NOW-timedelta(days=2)).isoformat()}
    outcomes=[{'horizon':'1d','evaluated_at':(NOW-timedelta(days=1)).isoformat(),
               'return':0.01,'benchmark_return':0.002}]
    out=h.forward_horizon_evaluator(decision,outcomes,now=NOW)
    assert out['horizons']['1d']['status']=='EVALUATED'
    assert out['horizons']['1w']['status']=='PENDING'
    assert out['horizons']['1w']['return'] is None


def test_23_attribution_identity_and_cost_sign():
    a={'signal':0.02,'regime':0.01,'selection':0.01,'timing':0.005,'sizing':0.0,
       'costs':-0.003,'residual':-0.002,'total_return':0.04,'max_abs_residual':0.01}
    assert h.attribution_gate(a)['status']=='PASS'
    assert h.attribution_gate({**a,'costs':0.003})['status']=='FAIL'


def test_24_meta_learning_is_bounded_challenger_only():
    c={'role':'challenger','forward_only':True,'backfilled':False,'forward_n':80,
       'forward_regimes':['bull','bear'],'parameter_deltas':{'w1':0.02,'w2':-0.03},
       'lineage_id':'l2','parent_lineage_id':'l1','mutates_active_champion':False,
       'automatic_promotion':False,'real_trading':False}
    out=h.meta_learning_gate(c)
    assert out['status']=='ELIGIBLE_SHADOW_PAPER'
    assert out['automatic_promotion'] is False
    assert h.meta_learning_gate({**c,'parameter_deltas':{'w1':0.2}})['status']=='REJECTED'


def test_25_scorecard_sample_aware_and_milestones_forward_only():
    metrics={'uptime_pct':99.0,'cycles':100,'decisions':80,'trades':20,'abstentions':60,
             'equity':1005,'pnl':5,'max_drawdown':0.02,'costs':1.2,'errors':1,
             'recoveries':1,'persistence_integrity':True,'accounting_integrity':True,
             'valid_forward_hours':80,'return_observations':10,'sharpe':2.0,'sortino':2.2}
    out=h.autonomous_paper_scorecard(metrics)
    assert out['status']=='COMPLETE'
    assert out['metrics']['sharpe'] is None
    assert out['milestones']['72h']=='PASS'
    assert out['milestones']['7d']=='PENDING'


def test_16_25_composite_preserves_hard_safety_boundaries():
    out=h.priorities_16_25_gate(
        lease={'status':'PASS'},runtime_chain={'status':'PASS'},watchdog={'status':'HEALTHY'},
        disasters={'status':'PASS'},reconciliation={'status':'RECONCILED'},journal={'status':'PASS'},
        horizons={'status':'PASS'},attribution={'status':'PASS'},
        meta_learning={'status':'ELIGIBLE_SHADOW_PAPER'},scorecard={'status':'COMPLETE'})
    assert out['status']=='PASS'
    assert out['paper_runtime_hardened'] is True
    assert out['live_execution_allowed'] is False
    assert out['automatic_promotion'] is False
    assert out['automatic_release'] is False
    assert out['setup_1_6_allowed'] is False
    assert out['real_trading'] is False
