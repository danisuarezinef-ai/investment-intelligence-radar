import sqlite3
import pytest
from radar_investment_memory import init_memory,freeze_prediction,evaluate_prediction
from radar_benchmark_lab_v2 import abstention_value,information_half_life
from radar_research_intelligence import research_queue,investment_committee,autonomous_research_proposal
from radar_market_context_v2 import narrative_saturation,cross_asset_confirmation,regime_transition
from radar_stress_v2 import stress_portfolio

def test_prediction_outcome_is_single_assignment():
 db=sqlite3.connect(':memory:');init_memory(db);clock=lambda:'2026-01-01T12:00:00+00:00';pid=freeze_prediction(db,{'symbol':'X','horizon':'1d','target_date':'2026-01-02T12:00:00+00:00','model_version':'v','provenance_snapshot':{'lookahead':False}},clock=clock)
 evaluate_prediction(db,pid,{'return':.01},'2026-01-02T12:00:00+00:00')
 with pytest.raises(ValueError):evaluate_prediction(db,pid,{'return':-.2})

def test_research_queue_prefers_value_of_information():
 q=research_queue([{'question':'a','decision_impact':1,'uncertainty':1,'resolvability':1,'cost':.1},{'question':'b','decision_impact':.1,'uncertainty':.1,'resolvability':.1,'cost':.1}])
 assert q[0]['question']=='a'

def test_committee_preserves_disagreement():
 x=investment_committee({'bull':{'score':1},'bear':{'score':-1}});assert x['disagreement']>0

def test_autonomous_research_cannot_promote_or_trade():
 x=autonomous_research_proposal({'question':'q'});assert x['promotion_allowed'] is False and x['real_trading'] is False

def test_narrative_crowding_matters():assert narrative_saturation(.9,.9,.9,.1)>narrative_saturation(.2,.2,.2,.9)
def test_cross_asset_conflict_detected():assert cross_asset_confirmation({'eq':1,'credit':-1})['conflict'] is True
def test_transition_points_to_rising_regime():assert regime_transition({'bull':.2,'bear':.8},{'bull':.8,'bear':.2})['toward']=='bear'
def test_stress_is_assumption_labelled():assert stress_portfolio({'A':1},{'A':{'technology':1}},'tech_drawdown')['assumption_based'] is True
def test_abstention_separates_avoided_and_missed():
 x=abstention_value([{'abstain':True,'outcome':-.2},{'abstain':True,'outcome':.1}]);assert x['avoided_loss']==.2 and x['missed_upside']==.1
def test_half_life():assert information_half_life({0:1,1:.8,2:.4})==2
