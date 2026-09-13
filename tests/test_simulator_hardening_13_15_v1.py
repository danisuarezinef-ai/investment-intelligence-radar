from datetime import datetime, timezone

import radar_simulator_hardening_13_15_v1 as h


def _good_day():
    return {
        'date':'2026-09-13',
        'opened_at':'2026-09-13T13:00:00+00:00',
        'closed_at':'2026-09-13T17:00:00+00:00',
        'evidence_class':'PROSPECTIVE_PAPER',
        'backfilled':False,
        'immutable':True,
        'summary_hash':'abc123',
        'start_equity':1000.0,
        'end_equity':1010.0,
        'net_pnl':10.0,
        'real_trading':False,
        'trades':[
            {'trade_id':'t1','decision_id':'d1','symbol':'MSFT','side':'BUY',
             'decision_at':'2026-09-13T13:30:00+00:00','ts':'2026-09-13T13:31:00+00:00',
             'paper':True,'backfilled':False,'real_trading':False,'quantity':1.0,'fill_price':100.0},
            {'trade_id':'t2','decision_id':'d2','symbol':'MSFT','side':'SELL',
             'decision_at':'2026-09-13T16:00:00+00:00','ts':'2026-09-13T16:01:00+00:00',
             'paper':True,'backfilled':False,'real_trading':False,'quantity':1.0,'fill_price':110.0},
        ],
    }


def _good_memory():
    return {
        'schema_version':'1','memory_store_id':'paper-memory-1','append_only':True,
        'checkpoint_hash':'cp1','exact_restore_required':True,'backfill_allowed':False,
        'real_trading':False,
        'entries':[
            {'memory_id':'m1','created_at':'2026-09-13T13:30:00+00:00','source_type':'DECISION',
             'source_id':'d1','content_hash':'h1','backfilled':False,'deleted':False,'mutated':False,'real_trading':False},
            {'memory_id':'m2','created_at':'2026-09-13T16:10:00+00:00','source_type':'OUTCOME',
             'source_id':'d1','content_hash':'h2','backfilled':False,'deleted':False,'mutated':False,'real_trading':False},
        ],
    }


def test_priority13_accepts_timestamped_immutable_prospective_paper_day():
    out=h.daily_paper_result_gate(_good_day())
    assert out['status']=='PASS_DAILY_PAPER'
    assert out['valid_trade_count']==2
    assert out['paper_execution_allowed'] is True
    assert out['live_execution_allowed'] is False
    assert out['real_trading'] is False


def test_priority13_blocks_backfill_or_trade_before_decision():
    day=_good_day()
    day['trades'][0]['backfilled']=True
    day['trades'][1]['ts']='2026-09-13T15:59:00+00:00'
    out=h.daily_paper_result_gate(day)
    assert out['status']=='BLOCKED_DAILY_PAPER'
    assert 'all_trades_valid' in out['blockers']
    errors=[e for row in out['trade_errors'] for e in row['errors']]
    assert 'backfilled' in errors
    assert 'trade_before_decision' in errors


def test_priority13_blocks_accounting_identity_mismatch():
    day=_good_day(); day['end_equity']=1020.0
    out=h.daily_paper_result_gate(day)
    assert out['status']=='BLOCKED_DAILY_PAPER'
    assert 'accounting_identity' in out['blockers']


def test_priority14_accepts_append_only_ordered_hashed_memory():
    out=h.memory_integrity_gate(_good_memory())
    assert out['status']=='PASS_MEMORY_INTEGRITY'
    assert out['learning_allowed'] is True
    assert out['silent_memory_rewrite_allowed'] is False
    assert out['entry_count']==2


def test_priority14_blocks_duplicate_mutated_or_backfilled_memory():
    memory=_good_memory()
    memory['entries'][1]['memory_id']='m1'
    memory['entries'][1]['mutated']=True
    memory['entries'][1]['backfilled']=True
    out=h.memory_integrity_gate(memory)
    assert out['status']=='BLOCKED_MEMORY_INTEGRITY'
    errors=[e for row in out['invalid_entries'] for e in row['errors']]
    assert 'duplicate_memory_id' in errors
    assert 'append_only_violation' in errors
    assert 'backfilled' in errors
    assert out['learning_allowed'] is False


def test_priority15_allows_only_bounded_forward_paper_learning():
    day=h.daily_paper_result_gate(_good_day())
    memory=h.memory_integrity_gate(_good_memory())
    candidate={
        'evidence_class':'PROSPECTIVE_PAPER','forward_only':True,'backfilled':False,
        'forward_observations':25,'confidence':0.72,'max_parameter_delta':0.05,
        'parameter_bounds_respected':True,'can_bypass_risk_gate':False,
        'can_bypass_promotion_gate':False,'automatic_model_replacement':False,
        'action':'BUY','real_trading':False,
    }
    out=h.autonomous_learning_gate(candidate=candidate,memory_gate=memory,daily_gate=day)
    assert out['status']=='PASS_BOUNDED_PAPER_LEARNING'
    assert out['action']=='BUY'
    assert out['learning_update_allowed'] is True
    assert out['automatic_model_replacement'] is False
    assert out['automatic_promotion'] is False
    assert out['live_execution_allowed'] is False


def test_priority15_abstains_on_low_evidence_or_oversized_parameter_jump():
    day=h.daily_paper_result_gate(_good_day())
    memory=h.memory_integrity_gate(_good_memory())
    candidate={
        'evidence_class':'PROSPECTIVE_PAPER','forward_only':True,'backfilled':False,
        'forward_observations':5,'confidence':0.50,'max_parameter_delta':0.40,
        'parameter_bounds_respected':True,'can_bypass_risk_gate':False,
        'can_bypass_promotion_gate':False,'automatic_model_replacement':False,
        'action':'BUY','real_trading':False,
    }
    out=h.autonomous_learning_gate(candidate=candidate,memory_gate=memory,daily_gate=day)
    assert out['status']=='ABSTAIN_LEARNING'
    assert out['action']=='ABSTAIN'
    assert 'minimum_forward_observations' in out['blockers']
    assert 'confidence_sufficient' in out['blockers']
    assert 'bounded_parameter_delta' in out['blockers']
    assert out['learning_update_allowed'] is False


def test_priority15_cannot_bypass_risk_or_promotion_gates():
    day=h.daily_paper_result_gate(_good_day())
    memory=h.memory_integrity_gate(_good_memory())
    candidate={
        'evidence_class':'PROSPECTIVE_PAPER','forward_only':True,'backfilled':False,
        'forward_observations':50,'confidence':0.90,'max_parameter_delta':0.01,
        'parameter_bounds_respected':True,'can_bypass_risk_gate':True,
        'can_bypass_promotion_gate':True,'automatic_model_replacement':True,
        'action':'BUY','real_trading':False,
    }
    out=h.autonomous_learning_gate(candidate=candidate,memory_gate=memory,daily_gate=day)
    assert out['status']=='ABSTAIN_LEARNING'
    assert 'risk_gate_cannot_be_bypassed' in out['blockers']
    assert 'promotion_gate_cannot_be_bypassed' in out['blockers']
    assert 'human_review_for_model_replacement' in out['blockers']


def test_priorities13_15_composite_keeps_live_and_release_frozen():
    day=h.daily_paper_result_gate(_good_day())
    memory=h.memory_integrity_gate(_good_memory())
    learning={'status':'ABSTAIN_LEARNING','real_trading':False}
    out=h.priorities_13_15_gate(daily=day,memory=memory,learning=learning)
    assert out['status']=='PASS'
    assert out['paper_runtime_supported'] is True
    assert out['automatic_promotion'] is False
    assert out['automatic_release'] is False
    assert out['live_execution_allowed'] is False
    assert out['setup_1_6_allowed'] is False
    assert out['real_trading'] is False
