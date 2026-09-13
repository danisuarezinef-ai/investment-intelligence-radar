import cloud_service_v12 as v12
import cloud_service_v10 as v10


def test_resilient_heartbeat_reacquires_same_owner_session(monkeypatch):
    with v10._LEASE_LOCK:
        v10._LEASE_STATE.update({'owner_id':'owner-a','session_id':'session-a','last':None,'last_error':None,'started':True})
    monkeypatch.setattr(v10.runtime_lease,'heartbeat',lambda *a,**k:{'held':False,'status':'LOST','error':'timeout','real_trading':False})
    monkeypatch.setattr(v10.runtime_lease,'acquire',lambda owner,session,ttl_seconds=180:{'held':True,'status':'HELD','lease':{'owner_id':owner,'session_id':session,'lease_name':'autonomous-paper','epoch':2,'heartbeat_at':'2026-09-13T19:00:00+00:00','expires_at':'2099-09-13T19:03:00+00:00','real_trading':False},'real_trading':False})
    out=v12.resilient_heartbeat_runtime_lease()
    assert out['held'] is True
    assert out['reacquired'] is True
    assert out['real_trading'] is False


def test_failed_reacquire_stays_fail_closed_without_mutating_user_enable_intent(monkeypatch):
    with v10._LEASE_LOCK:
        v10._LEASE_STATE.update({'owner_id':'owner-b','session_id':'session-b','last':None,'last_error':None,'started':True})
    monkeypatch.setattr(v10.runtime_lease,'heartbeat',lambda *a,**k:{'held':False,'status':'LOST','error':'500','real_trading':False})
    monkeypatch.setattr(v10.runtime_lease,'acquire',lambda *a,**k:{'held':False,'status':'BLOCKED','error':'conflict','real_trading':False})
    out=v12.resilient_heartbeat_runtime_lease()
    assert out['held'] is False
    assert out['reacquired'] is False
    assert out['real_trading'] is False


def test_exact_autonomy_core_is_required_before_first_admission(monkeypatch):
    monkeypatch.setattr(v12.autonomy_core,'restore_exact_core',lambda sim:{'status':'BLOCKED_AUTONOMY_CORE','restored':False,'error':'authority unavailable','real_trading':False})
    v12._CORE_RESTORED=False
    out=v12._restore_autonomy_core_once()
    assert out['restored'] is False
    assert v12._CORE_RESTORED is False
    assert v12.base11.admission_status()['paper_execution_allowed'] is False


def test_exact_autonomy_core_preserves_durable_counters(monkeypatch):
    monkeypatch.setattr(v12.autonomy_core,'restore_exact_core',lambda sim:{'status':'RESTORED_EXACT_AUTONOMY_CORE','restored':True,'generation':15,'completed_cycles':350,'completed_experiments':84,'real_trading':False})
    monkeypatch.setattr(v12.autonomy_core,'local_state',lambda sim:{'enabled':1,'generation':15,'completed_cycles':350,'completed_experiments':84})
    v12._CORE_RESTORED=False
    out=v12._restore_autonomy_core_once()
    assert out['restored'] is True
    assert out['completed_cycles']==350
    assert out['completed_experiments']==84
    assert v12._CORE_RESTORED is True


def test_reconciliation_pair_detects_cycle_divergence(monkeypatch):
    cp={'state_hash':'h','observed_at':'2026-09-13T19:00:00+00:00','tables':{
        'paper_agent_positions':[{'agent_id':'a','symbol':'X','qty':1}],
        'champion_paper_positions':[{'symbol':'X','qty':1}],
        'champion_paper_marks':[{'cash':100,'total':200}]}}
    monkeypatch.setattr(v12.paper_persistence,'engine_checkpoint',lambda:cp)
    monkeypatch.setattr(v12.autonomy_core,'local_state',lambda sim:{'status':'ACTIVE','generation':15,'completed_cycles':351,'completed_experiments':84,'queued_experiments':0,'last_cycle_at':'2026-09-13T19:00:00+00:00','last_research_at':'2026-09-13T18:00:00+00:00','next_cycle_at':'2026-09-13T19:15:00+00:00','next_research_at':'2026-09-14T00:00:00+00:00'})
    monkeypatch.setattr(v12.base11,'admission_status',lambda:{'session_id':'s','status':'READY_EXACT_PAPER'})
    remote={'ok':True,'checkpoint':{'state_hash':'h','observed_at':'2026-09-13T19:00:00+00:00','paper_positions':[{'agent_id':'a','symbol':'X','qty':1}],'champion_positions':[{'symbol':'X','qty':1}],'champion_cash':'100','champion_total':'200'},
            'autonomy':{'payload':{'status':'ACTIVE','generation':15,'completed_cycles':350,'completed_experiments':84,'queued_experiments':0,'last_cycle_at':'2026-09-13T19:00:00+00:00','last_research_at':'2026-09-13T18:00:00+00:00','next_cycle_at':'2026-09-13T19:15:00+00:00','next_research_at':'2026-09-14T00:00:00+00:00'}},
            'lease':{'session_id':'s'}}
    local,far=v12._reconciliation_pair(remote)
    gate=v12.tasks2130.hard.persistence_reconciliation_gate(local,far)
    assert gate['status']=='CRITICAL_PERSISTENCE_DIVERGENCE'
    assert 'cycle' in gate['mismatched_fields']
    assert gate['new_paper_risk_allowed'] is False


def test_runtime_board_never_authorizes_live(monkeypatch):
    monkeypatch.setattr(v12.base9.autonomous_paper.simulator,'simulator_status',lambda:{'paper':{},'completed_cycles':350,'real_trading':False})
    monkeypatch.setattr(v12.base9.autonomous_paper,'milestones',lambda:{'valid_forward_hours':None,'real_trading':False})
    monkeypatch.setattr(v12,'_restore_state',lambda:{'status':'RESTORED_EXACT_PAPER_ENGINE','verified':True,'remote_state_hash':'a','local_state_hash':'a','backfill_used':False,'reconstructed':False,'real_trading':False})
    monkeypatch.setattr(v12,'_lease_local',lambda:{'held':True,'status':'HELD','real_trading':False})
    monkeypatch.setattr(v12.remote_evidence,'summary',lambda:{'ok':False,'status':'FAIL_CLOSED','real_trading':False})
    monkeypatch.setattr(v12,'_reconciliation_pair',lambda remote=None:({'real_trading':False},{'real_trading':False}))
    monkeypatch.setattr(v12.tasks2130,'board',lambda **kwargs:{'tasks':[],'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'real_trading':False})
    out=v12.runtime_board()
    assert out['real_trading'] is False
    assert out['live_execution_allowed'] is False
    assert out['automatic_promotion'] is False
    assert out['automatic_release'] is False
    assert out['setup_1_6_allowed'] is False


def test_paper_calls_require_ready_and_reconciled(monkeypatch):
    calls=[]
    wrapped=v12._gate_paper_call('probe',lambda: calls.append('executed') or {'status':'OK'}, {'paper_execution_allowed':False})
    monkeypatch.setattr(v12,'_ready',lambda:True)
    v12._DURABLE_SYNC={'status':'DEGRADED','real_trading':False}
    out=wrapped()
    assert out['status']=='BLOCKED_EXACT_RECOVERY'
    assert calls==[]
    v12._DURABLE_SYNC={'status':'RECONCILED','real_trading':False}
    out=wrapped()
    assert out['status']=='OK'
    assert calls==['executed']
