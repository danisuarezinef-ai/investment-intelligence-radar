from radar_block_g_learning_v1 import *

def test_block_g_validation():
    r=block_g_validation()
    assert r['status']=='PASS'
    assert r['autonomous_learning_loop']=='ACTIVE'
    assert r['real_trading'] is False
    assert r['learning_run']['formal_forward_maturity_samples']==0

def test_abstention_has_learning_value():
    m=seed_lineage('balanced')
    e=record_outcome(m,action='NO_INVERTIR',realized_return=-.01,benchmark_return=-.03,confidence=.7,evidence_kind='vault',horizon='1w')
    assert e['avoided_loss']>0
    assert e['audited_forward_maturity_credit'] is False

def test_mutation_lineage_is_traceable():
    p=seed_lineage('balanced'); c=mutate(p,'risk_weight',.03)
    assert c['parent']==p['model_id'] and c['generation']==1 and c['status']=='CHALLENGER'

def test_live_forward_is_only_formal_maturity_credit():
    m=seed_lineage('balanced')
    a=record_outcome(m,action='BUY',realized_return=.01,evidence_kind='walk_forward',horizon='1d')
    b=record_outcome(m,action='BUY',realized_return=.01,evidence_kind='live_forward',horizon='1d')
    assert a['audited_forward_maturity_credit'] is False
    assert b['audited_forward_maturity_credit'] is True
