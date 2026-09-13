import radar_portfolio_intelligence_61_70_v1 as h

def rows(n=40):
    out=[]
    for i in range(n):
        out.append({'prediction_id':str(i),'created_at':f'2026-09-{1+i//16:02d}T12:00:00+00:00','evaluated_at':f'2026-09-{2+i//16:02d}T12:00:00+00:00',
                    'symbol':['MSFT','NVDA','META'][i%3],'horizon':'1d','confidence':.55+.01*(i%10),'uncertainty':{'regime':'risk_on_growth'},
                    'decision_state':'BUY' if i%3 else 'WAIT','matured':True,'natural':True,'net_return':.01 if i%2 else -.004,
                    'cost':.001,'excess_return':.005 if i%2 else -.006,'outcome':{'return':.012 if i%2 else -.003},'real_trading':False})
    return out

def agents():
    return [{'agent_id':'conservative','pnl_pct':2.0,'sharpe':1.0,'max_drawdown_pct':-2.0,'marks':30,'positions':[],'trades':[]},
            {'agent_id':'balanced','pnl_pct':3.0,'sharpe':1.2,'max_drawdown_pct':-3.0,'marks':30,'positions':[],'trades':[]}]

def test_board_has_exact_tasks_and_no_live_authority():
    b=h.board(rows(),agents(),{'total':200})
    assert set(b['tasks'])=={str(i) for i in range(61,71)}
    assert b['automatic_promotion'] is False and b['live_execution_allowed'] is False and b['real_trading'] is False

def test_liquidity_missing_is_not_imputed():
    x=h.liquidity_stress(rows());assert x['status']=='PENDING_DATA';assert x['missing_liquidity_is_not_imputed'] is True

def test_tail_stress_cannot_mature_forward_gate():
    x=h.tail_event_simulator(rows(),{'total':200});assert x['status']=='PASS';assert x['cannot_mature_forward_gate'] is True

def test_dynamic_ensemble_is_shadow_only():
    x=h.dynamic_ensemble(agents());assert x['status']=='PASS';assert x['weights_are_shadow_advisory'] is True;assert x['automatic_execution'] is False

def test_agent_specialization_does_not_fake_regime_horizon_attribution():
    x=h.agent_specialization_map(agents());assert x['status']=='PARTIAL_CONTEXT';assert all(v['regime_horizon_specialization_verified'] is False for v in x['agents'].values())
