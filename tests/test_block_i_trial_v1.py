from radar_block_i_trial_v1 import *

def test_trial_002_passes_and_is_paper_only():
    r=block_i_validation()
    assert r['status']=='PASS'
    assert r['paper_trial_002']=='VERIFIED'
    assert r['real_trading'] is False

def test_learned_policy_changes_selection():
    r=run_trial_002()
    assert r['learned_symbols'] != r['baseline_symbols']
    assert r['rejected_symbols']

def test_no_false_forward_credit():
    r=run_trial_002()
    assert r['formal_forward_maturity_samples']==0
    assert r['evidence_label']=='ACCELERATED_PAPER_NOT_AUDITED_FORWARD'
