from radar_paper_certification_131_160_v1 import (
    accounting_proof,
    position_lifecycle,
    learning_chain,
    prospective_arena,
    mutation_sandbox,
    learning_rollback,
    catastrophic_guard,
    recovery_stress,
)


def test_block_c_151_158_happy_path_is_paper_only():
    results = [
        accounting_proof({
            'cash': 100.0, 'positions_value': 50.0, 'realized_pnl': 5.0,
            'unrealized_pnl': -2.0, 'equity': 153.0,
            'persisted_reconciled': True,
        }),
        position_lifecycle([
            {'position_id': 'p1', 'event': event}
            for event in ('OPEN', 'MANAGE', 'CLOSE', 'PNL', 'EVALUATE')
        ]),
        learning_chain([{
            'decision_id': 'd1', 'order_id': 'o1', 'outcome_id': 'out1',
            'learning_event_id': 'l1', 'next_policy_id': 'policy2',
            'temporal_order_valid': True,
        }]),
        prospective_arena({
            'forward_only': True, 'matched_cells': True, 'challengers': 1,
            'forward_n': 40, 'forward_days': 14,
        }),
        mutation_sandbox({
            'isolated': True, 'shadow_only': True, 'no_champion_mutation': True,
            'no_live_authority': True, 'state_namespace_separate': True,
        }),
        learning_rollback({
            'snapshot_before': 'h1', 'snapshot_after': 'h2',
            'rollback_tested': True, 'hash_restored': True,
        }),
        catastrophic_guard({
            'freeze_on_drawdown': True, 'freeze_on_corruption': True,
            'freeze_on_unknown_regime': True, 'freeze_on_runtime_failure': True,
            'manual_unfreeze_required': True,
        }),
        recovery_stress([
            {'scenario': s, 'result': 'EXACT_RECOVERY'}
            for s in (
                'process_kill', 'supabase_outage', 'market_data_outage', 'timeout',
                'redeploy', 'duplicate_instance', 'hung_process', 'restart_mid_persist'
            )
        ]),
    ]
    assert [r['task'] for r in results] == list(range(151, 159))
    assert all(r['status'] == 'PASS' for r in results)
    assert all(r['real_trading'] is False for r in results)
    assert all(r['evidence']['real_trading'] is False for r in results)


def test_block_c_fail_closed_and_pending_paths():
    assert accounting_proof({
        'cash': 100, 'positions_value': 50, 'realized_pnl': 5,
        'unrealized_pnl': -2, 'equity': 154, 'persisted_reconciled': True,
    })['status'] == 'FAIL_CLOSED'
    assert position_lifecycle([{'position_id': 'p1', 'event': 'OPEN'}])['status'] == 'PARTIAL'
    assert learning_chain([{
        'decision_id': 'd1', 'order_id': 'o1', 'outcome_id': 'out1',
        'learning_event_id': 'l1', 'next_policy_id': 'policy2',
        'temporal_order_valid': False,
    }])['status'] == 'FAIL_CLOSED'
    assert prospective_arena({'forward_only': True, 'matched_cells': True, 'challengers': 1, 'forward_n': 39, 'forward_days': 14})['status'] == 'PENDING_SAMPLE'
    assert mutation_sandbox({'isolated': True})['status'] == 'PENDING_IMPLEMENTATION'
    assert learning_rollback({'snapshot_before': 'h1'})['status'] == 'PENDING_PROOF'
    assert catastrophic_guard({'freeze_on_drawdown': True})['status'] == 'PENDING_IMPLEMENTATION'
    assert recovery_stress([{'scenario': 'process_kill', 'result': 'EXACT_RECOVERY'}])['status'] == 'PENDING_PROOF'
