import radar_operational_closure_101_120_v1 as m

def test_no_calendar_maturity():
    b=m.board(intervals=[])
    d={x['task']:x for x in b['tasks']}
    assert d[108]['status']=='PENDING_TIME' and d[110]['status']=='PENDING_TIME'
    assert b['real_trading'] is False and b['live_execution_allowed'] is False

def test_only_healthy_intervals_credit():
    base={'start':'2026-09-01T00:00:00Z','end':'2026-09-04T00:00:00Z','exact_restore':True,'singleton':True,'persistence_reconciled':True,'market_data_ok':True,'backfill':False}
    b=m.board(intervals=[{**base,'healthy':True}]);d={x['task']:x for x in b['tasks']}
    assert b['audited_valid_forward_hours']==72 and d[108]['status']=='PASS' and d[109]['status']=='PENDING_TIME'
    bad=m.board(intervals=[{**base,'healthy':False}]);assert bad['audited_valid_forward_hours']==0

def test_liquidity_never_imputed():
    d={x['task']:x for x in m.board(liquidity={'observed_volume':10})['tasks']}
    assert d[117]['status']=='PENDING_DATA' and d[117]['evidence']['imputed'] is False

def test_fail_closed_accounting_and_singleton():
    d={x['task']:x for x in m.board(singleton={'active_instances':2},accounting={'reconciled':False})['tasks']}
    assert d[113]['status']=='FAIL_CLOSED' and d[119]['status']=='FAIL_CLOSED'

def test_exact_tasks_101_120():
    b=m.board();assert [x['task'] for x in b['tasks']]==list(range(101,121))
    assert b['automatic_promotion'] is False and b['automatic_release'] is False and b['setup_1_6_allowed'] is False
