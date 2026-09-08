import pytest
from radar_decision_lab_v4 import *

def test_thesis_lifecycle_and_invalid_transition():
 assert thesis_transition('NEW','activate')=='ACTIVE'
 assert thesis_transition('ACTIVE','kill')=='INVALIDATED'
 with pytest.raises(ValueError):thesis_transition('CLOSED','activate')
def test_forward_prediction_is_fingerprinted_and_safe():
 x=freeze_forward_prediction({'symbol':'X','horizon':'1d'});assert x['immutable'] and x['real_trading'] is False and len(x['fingerprint'])==64
def test_selective_prediction_reports_coverage():
 x=selective_curve([{'confidence':.9,'outcome':1},{'confidence':.2,'outcome':-1}],(.5,));assert x[0]['coverage']==.5 and x[0]['mean_outcome']==1
def test_expected_shortfall_uses_bad_tail():assert expected_shortfall([-.5,-.1,.1,.2],.25)==-.5
def test_stale_decay_half_life():assert stale_decay(10,10)==.5
def test_duplicates_cluster():assert len(cluster_duplicates([{'story_fingerprint':'a'},{'story_fingerprint':'a'}]))==1
def test_survivorship_audit_is_conservative():assert survivorship_audit(False,True,True)['survivorship_bias_risk'] is True
def test_autonomous_sandbox_cannot_promote_trade():
 x=autonomous_sandbox({'q':'x'});assert x['can_promote'] is False and x['can_trade'] is False
def test_complexity_must_earn_keep():assert baseline_challenge(.4,.5)['keep_complexity'] is False
def test_release_audit_requires_all_and_no_real_trading():assert final_release_audit(True,True,True,True,False)['pass'] is True
def test_release_audit_blocks_real_trading():assert final_release_audit(True,True,True,True,True)['pass'] is False
def test_evidence_conflict_penalty():assert evidence_conflict([{'claim':'x','value':1},{'claim':'x','value':2}])[0]['penalty']>0
def test_pit_membership_requires_known_at():
 rows=[{'asset':'A','valid_from':'2020','valid_to':None,'known_at':'2025'}];assert pit_membership('A','2024',rows) is False
def test_regret_is_hindsight_labelled():assert regret(-.1,.2)['hindsight_only'] is True
def test_real_trading_off():assert REAL_TRADING is False
