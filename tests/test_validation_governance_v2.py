from radar_validation_governance_v2 import walk_forward_audit,shadow_evidence_summary,validation_gate,degradation_action


def _fold(i):
    return {'train_start':f'2026-01-0{i}T00:00:00+00:00','train_end':f'2026-01-1{i}T00:00:00+00:00',
            'validation_start':f'2026-01-2{i}T00:00:00+00:00','validation_end':f'2026-01-2{i}T23:00:00+00:00',
            'observations_train':100,'observations_validation':20,'holdout':True,'lookahead':False}


def _strong():
    return {'forward_days':120,'matured_predictions':150,'decisions':80,'max_drawdown_pct':-6,
            'brier':.16,'hit_rate':.58,'excess_return_pct':4.0,'positive_months':4,
            'ledger_integrity':True,'pit_verified':True,'costs_included':True}


def test_walk_forward_requires_chronological_holdout():
    out=walk_forward_audit([_fold(1),_fold(2),_fold(3),_fold(4)])
    assert out['pass'] is True
    bad=_fold(1);bad['validation_start']='2026-01-05T00:00:00+00:00'
    out=walk_forward_audit([bad,_fold(2),_fold(3),_fold(4)])
    assert out['pass'] is False
    assert 1 in out['violations']


def test_shadow_summary_rejects_backfill_and_mutable_rows():
    rows=[
      {'created_at':'2026-02-02T00:00:00+00:00','evaluated_at':'2026-02-03T00:00:00+00:00','immutable':True,'matured':True,'return_pct':2},
      {'created_at':'2026-01-01T00:00:00+00:00','evaluated_at':'2026-02-03T00:00:00+00:00','immutable':True,'matured':True,'return_pct':5},
      {'created_at':'2026-02-02T00:00:00+00:00','evaluated_at':'2026-02-03T00:00:00+00:00','immutable':False,'matured':True,'return_pct':5},
    ]
    out=shadow_evidence_summary(rows,'2026-02-01T00:00:00+00:00')
    assert out['valid_matured']==1
    assert len(out['invalid_records'])==2
    assert out['mean_return_pct']==2


def test_validation_gate_never_trades_and_requires_all_layers():
    folds=[_fold(1),_fold(2),_fold(3),_fold(4)]
    ref={'hit_rate':.60,'brier':.15,'excess_return_pct':3,'max_drawdown_pct':-5}
    cur={'hit_rate':.59,'brier':.16,'excess_return_pct':2,'max_drawdown_pct':-6}
    out=validation_gate(_strong(),folds,ref,cur)
    assert out['ready_for_live_review'] is True
    assert out['can_trade'] is False
    assert out['auto_promote'] is False
    assert out['real_trading'] is False


def test_degradation_blocks_review():
    folds=[_fold(1),_fold(2),_fold(3),_fold(4)]
    ref={'hit_rate':.65,'brier':.12,'excess_return_pct':7,'max_drawdown_pct':-4}
    cur={'hit_rate':.45,'brier':.25,'excess_return_pct':0,'max_drawdown_pct':-12}
    out=validation_gate(_strong(),folds,ref,cur)
    assert out['ready_for_live_review'] is False
    assert 'performance_degradation' in out['blockers']


def test_incomplete_degradation_evidence_fails_closed():
    folds=[_fold(1),_fold(2),_fold(3),_fold(4)]
    out=validation_gate(_strong(),folds,{'hit_rate':.6},{'hit_rate':.59})
    assert out['ready_for_live_review'] is False
    assert 'degradation_evidence_incomplete' in out['blockers']


def test_degradation_action_recommends_only():
    out=degradation_action({'evidence_complete':True,'degraded':True},1.0)
    assert out['recommended_multiplier']==.5
    assert out['automatic_application'] is False
    assert out['real_trading'] is False
