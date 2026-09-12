from datetime import datetime, timezone, timedelta

import radar_autonomous_paper_control_v1 as ctl


def _sim(**kw):
    base={'active':True,'status':'ACTIVE','generation':4,'completed_cycles':20,'completed_experiments':30,
          'last_cycle_at':datetime.now(timezone.utc).isoformat(),'last_research_at':datetime.now(timezone.utc).isoformat(),
          'last_error':None,'paper':{'enabled':True,'total':1010.0,'cash':600.0,'invested':410.0,'pnl_pct':1.0},
          'automatic_live_promotion':False,'forward_evidence_mutated':False,'real_trading':False,
          'recent_runs':[],'experiment_memory':{'count':30}}
    base.update(kw);return base


def test_simulator_gate_is_independent_from_brain_profitability(monkeypatch):
    monkeypatch.setattr(ctl.simulator,'simulator_status',lambda:_sim())
    monkeypatch.setattr(ctl.persistence,'enabled',lambda:True)
    gate=ctl.simulator_gate(technical={'status':'HEALTHY'},brain={'status':'PRE160_TASKS_311_370','brain_readiness_gate':{'status':'NOT_READY'}})
    assert gate['status']=='SIMULATOR_READY'
    assert gate['brain_readiness_required'] is False
    assert gate['positive_alpha_required_to_simulate'] is False
    assert gate['task_150_required_to_simulate'] is False
    assert gate['live_execution_allowed'] is False
    assert gate['automatic_promotion'] is False
    assert gate['real_trading'] is False


def test_gate_fails_closed_if_paper_or_persistence_missing(monkeypatch):
    monkeypatch.setattr(ctl.simulator,'simulator_status',lambda:_sim(paper={'enabled':False}))
    monkeypatch.setattr(ctl.persistence,'enabled',lambda:False)
    gate=ctl.simulator_gate()
    assert gate['status']=='NOT_READY'
    assert 'paper_enabled' in gate['blockers']
    assert 'remote_checkpoint_configured' in gate['blockers']
    assert gate['real_trading'] is False


def test_watchdog_only_emits_operational_alerts(monkeypatch):
    old=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    monkeypatch.setattr(ctl.simulator,'simulator_status',lambda:_sim(last_cycle_at=old))
    w=ctl.watchdog_status(cycle_interval_seconds=900)
    assert 'SIMULATOR_CYCLE_STALE' in w['alerts']
    assert w['alert_scope']=='OPERATIONAL_ONLY_NO_TRADE_SPAM'
    assert w['real_trading'] is False


def test_milestones_cannot_be_backfilled(monkeypatch):
    started=(datetime.now(timezone.utc)-timedelta(hours=80)).isoformat()
    monkeypatch.setattr(ctl,'_load_or_create_session',lambda:{'session_id':'x','started_at':started})
    monkeypatch.setattr(ctl.simulator,'simulator_status',lambda:_sim())
    m=ctl.milestones()
    assert m['milestones']['72h']['status']=='PASS'
    assert m['milestones']['7d']['status']=='PENDING_TIME'
    assert m['milestones']['30d']['status']=='PENDING_TIME'
    assert all(x['backfill_allowed'] is False for x in m['milestones'].values())


def test_learning_agenda_is_research_only():
    brain={'tasks':{'355':{'evidence':{'mean_net_return':-0.001}},'350':{'state':'FAILED'},'336':{'evidence':{'1d':{'status':'PASS'},'1w':{'status':'PENDING_SAMPLE'}}}}}
    a=ctl.learning_agenda(brain)
    assert a['priority']=='IMPROVE_FORWARD_NET_ALPHA'
    assert a['observed_mean_net_return']<0
    assert a['historical_can_promote'] is False
    assert a['automatic_champion_replacement'] is False
    assert all(x['forward_promotion'] is False for x in a['experiments'])
    assert a['real_trading'] is False


def test_control_never_starts_duplicate_simulator_daemon():
    src=open(ctl.__file__,encoding='utf-8').read()
    assert 'simulator.autonomous_simulator_loop(' not in src
    assert "duplicate_simulator_started':False" in src
    assert ctl.REAL_TRADING is False
