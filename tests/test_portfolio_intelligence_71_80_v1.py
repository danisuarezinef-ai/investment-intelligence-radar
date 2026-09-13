import radar_portfolio_intelligence_71_80_v1 as h

def price_series():
    return {'A':[('2026-09-01',100),('2026-09-02',101),('2026-09-03',102),('2026-09-04',103)],
            'B':[('2026-09-01',100),('2026-09-02',99),('2026-09-03',101),('2026-09-04',100)],
            'C':[('2026-09-01',100),('2026-09-02',102),('2026-09-03',101),('2026-09-04',104)]}

def portfolio():
    return {'total':100.0,'positions':[{'symbol':'MSFT','value':20.0},{'symbol':'NVDA','value':20.0},{'symbol':'LLY','value':10.0}], 'real_trading':False}

def rows(n=40):
    out=[]
    for i in range(n):out.append({'matured':True,'natural':True,'symbol':'MSFT' if i%2==0 else 'NVDA','net_return':.01 if i%3 else -.02})
    return out

def test_71_correlation_is_observational():
    x=h.correlation_intelligence(price_series());assert x['real_trading'] is False;assert x['can_increase_risk'] is False

def test_72_75_never_create_orders():
    sig=[{'symbol':'MSFT','horizon':'1d','confidence':.8,'uncertainty':{'regime':'risk_on'},'matured':False}]
    c=h.concentration_risk(portfolio());d=h.diversification_score(portfolio(),h.correlation_intelligence(price_series()));s=h.dynamic_position_sizing(sig,portfolio(),{});r=h.risk_budget_allocator(sig,portfolio())
    assert c['real_trading'] is False and d['real_trading'] is False
    assert s['orders_created'] is False and r['orders_created'] is False

def test_77_79_stress_gives_no_maturity_credit():
    assert h.correlation_breakdown_stress(portfolio())['maturity_credit'] is False
    assert h.sector_shock_stress(portfolio())['maturity_credit'] is False
    assert h.liquidity_crisis_stress(portfolio(),{})['status']=='PENDING_DATA'

def test_80_survival_gate_fail_closed_without_evidence():
    x=h.portfolio_survival_gate(portfolio(),{'status':'PENDING_SAMPLE'},{'status':'PENDING_SAMPLE'},h.correlation_breakdown_stress(portfolio()),h.sector_shock_stress(portfolio()),{'status':'PENDING_DATA'})
    assert x['status']=='BLOCKED_EVIDENCE';assert x['new_paper_risk_allowed'] is False;assert x['live_execution_allowed'] is False;assert x['real_trading'] is False

def test_board_is_71_80_and_paper_only():
    b=h.board(rows(),[],portfolio(),price_series(),[],{})
    assert set(b['tasks'])=={str(i) for i in range(71,81)}
    assert b['automatic_promotion'] is False and b['automatic_release'] is False and b['live_execution_allowed'] is False and b['real_trading'] is False
