from datetime import datetime,timezone,timedelta
import radar_policy_intelligence_81_90_v1 as h

def rows(n=60):
    t=datetime(2026,9,1,tzinfo=timezone.utc);out=[]
    acts=['BUY','SELL','WAIT']
    for i in range(n):
        a=acts[i%3];ret=.012 if i%4 in (0,1) else -.008
        out.append({'prediction_id':str(i),'created_at':(t+timedelta(hours=i)).isoformat(),'evaluated_at':(t+timedelta(hours=i+24)).isoformat(),
          'symbol':'MSFT' if i%2==0 else 'NVDA','horizon':'1d','model_version':'m1','confidence':.48+.005*(i%40),
          'uncertainty':{'regime':'risk_on_growth','epistemic':.2},'decision_state':a,'matured':True,'natural':True,
          'net_return':ret,'gross_return':ret+.001,'cost':.001,'benchmark_return':.003,'excess_return':ret-.003,
          'quality_checks':{'pit_valid':True,'backfilled':False},'provenance':{'lookahead':False},'real_trading':False})
    return out

def test_board_has_81_90_and_hard_safety():
    b=h.board(rows());assert set(b['tasks'])=={str(i) for i in range(81,91)}
    assert b['real_trading'] is False and b['automatic_promotion'] is False and b['live_execution_allowed'] is False

def test_causal_graph_does_not_claim_causality():
    x=h.decision_causal_graph(rows());assert x['status']=='PASS';assert x['edge_semantics']=='EXPLANATORY_NOT_CAUSAL'
    assert all(g['causal_proof'] is False for g in x['graphs'])

def test_counterfactual_replay_gets_no_maturity_credit():
    x=h.counterfactual_portfolio_replay(rows());assert x['maturity_credit'] is False and x['state_mutation'] is False

def test_policy_comparison_cannot_switch_automatically():
    x=h.policy_comparison(rows());assert x['automatic_policy_switch'] is False;assert x['counterfactual_only'] is True

def test_challenger_requires_new_forward_test_and_cannot_promote():
    x=h.adaptive_policy_challenger(rows());assert x['automatic_replacement'] is False;assert x['automatic_promotion'] is False
    assert x['requires_new_prospective_forward_test'] is True and x['counterfactual_results_cannot_promote'] is True

def test_regret_has_no_operational_lookahead():
    x=h.regret_minimization_score(rows());assert x['no_operational_lookahead'] is True;assert x['uses_outcomes_only_after_evaluation'] is True
