import radar_paper_certification_131_160_v1 as m


def test_exact_tasks_and_hard_locks():
    b=m.board()
    assert list(b['tasks'])==[str(x) for x in range(131,161)]
    assert b['real_trading'] is False and b['live_execution_allowed'] is False
    assert b['automatic_promotion'] is False and b['automatic_release'] is False and b['setup_1_6_allowed'] is False


def test_certification_gate_requires_720h_and_all_critical():
    critical=(131,132,133,134,135,136,137,138,139,140,141,142,143,145,146,147,148,149,150,151,152,153,155,156,157,158,159)
    states={str(n):'PASS' for n in critical}
    assert m.certification_gate(states,719)['status']=='BLOCKED'
    assert m.certification_gate(states,720)['status']=='CERTIFIED_PAPER_AUTONOMOUS'
    assert m.certification_gate(states,720)['evidence']['live_execution_allowed'] is False


def test_lookahead_fails_closed():
    x=m.no_lookahead_monitor([{'prediction_id':'p1','quality_checks':{'lookahead':True}}])
    assert x['status']=='FAIL_CLOSED'


def test_feature_coverage_requires_all_prospective_valid():
    rows=[{'prospective_capture':True,'features':{'x':1},'feature_fingerprint':'h','immutable':True,'backfilled':False}]
    assert m.feature_coverage(rows)['status']=='PASS'
    rows.append({'prospective_capture':True,'features':{},'feature_fingerprint':'h','immutable':True,'backfilled':False})
    assert m.feature_coverage(rows)['status']=='FAIL_CLOSED'


def test_liquidity_never_imputed():
    assert m.liquidity_v2([{'spread':.001,'volume':1000,'observed_at':'2026-09-14T00:00:00Z','source':'x'}])['status']=='PASS'
    assert m.liquidity_v2([{'volume':1000}])['status']=='PENDING_DATA'


def test_execution_requires_idempotency_and_realism():
    e={k:True for k in ('partial_fills','rejects','cancellations','market_hours','spread','slippage','commissions','liquidity_limits','idempotency_key')}
    assert m.execution_v3(e)['status']=='PASS'
    e['slippage']=False
    assert m.execution_v3(e)['status']=='PENDING_IMPLEMENTATION'


def test_accounting_equation_fail_closed():
    good={'cash':50,'positions_value':40,'realized_pnl':5,'unrealized_pnl':5,'equity':100,'persisted_reconciled':True}
    assert m.accounting_proof(good)['status']=='PASS'
    bad=dict(good,equity=101)
    assert m.accounting_proof(bad)['status']=='FAIL_CLOSED'


def test_recovery_suite_requires_all_scenarios():
    req=('process_kill','supabase_outage','market_data_outage','timeout','redeploy','duplicate_instance','hung_process','restart_mid_persist')
    x=m.recovery_stress([{'scenario':s,'result':'FAIL_CLOSED'} for s in req])
    assert x['status']=='PASS'


def test_mutation_sandbox_has_no_live_authority():
    x=m.mutation_sandbox({'isolated':True,'shadow_only':True,'no_champion_mutation':True,'no_live_authority':True,'state_namespace_separate':True})
    assert x['status']=='PASS' and x['real_trading'] is False
