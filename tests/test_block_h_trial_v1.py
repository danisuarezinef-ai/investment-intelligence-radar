from radar_block_h_trial_v1 import *

def test_first_trial_technical_pass():
    r=block_h_validation()
    assert r['status']=='PASS'
    assert r['first_paper_trial']=='VERIFIED'
    assert r['real_trading'] is False

def test_trial_is_frozen_and_reproducible():
    a=run_trial(); b=run_trial()
    assert a['config']['config_hash']==b['config']['config_hash']
    assert a['ending_equity']==b['ending_equity']
    assert a['radar_top3']==b['radar_top3']

def test_no_accelerated_evidence_becomes_forward_maturity():
    r=run_trial()
    assert r['formal_forward_maturity_samples']==0
    assert r['trial_evidence_label']=='ACCELERATED_PAPER_NOT_AUDITED_FORWARD'

def test_benchmarks_and_nontrades_present():
    r=run_trial()
    assert r['non_buys']>0
    assert {'cash_return','equal_weight_return','index_proxy_return'} <= set(r['benchmarks'])
