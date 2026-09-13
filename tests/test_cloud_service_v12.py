import cloud_service_v12 as v12
import cloud_service_v10 as v10
import cloud_service_v11 as v11


def test_resilient_heartbeat_reacquires_same_owner_session(monkeypatch):
    with v10._LEASE_LOCK:
        v10._LEASE_STATE.update({'owner_id':'owner-a','session_id':'session-a','last':None,'last_error':None,'started':True})
    monkeypatch.setattr(v10.runtime_lease,'heartbeat',lambda *a,**k:{'held':False,'status':'LOST','error':'timeout','real_trading':False})
    monkeypatch.setattr(v10.runtime_lease,'acquire',lambda owner,session,ttl_seconds=180:{'held':True,'status':'HELD','owner_id':owner,'session_id':session,'real_trading':False})
    out=v12.resilient_heartbeat_runtime_lease()
    assert out['held'] is True
    assert out['reacquired'] is True
    assert out['owner_id']=='owner-a'
    assert out['session_id']=='session-a'
    assert out['real_trading'] is False


def test_failed_reacquire_disables_paper(monkeypatch):
    disabled=[]
    with v10._LEASE_LOCK:
        v10._LEASE_STATE.update({'owner_id':'owner-b','session_id':'session-b','last':None,'last_error':None,'started':True})
    monkeypatch.setattr(v10.runtime_lease,'heartbeat',lambda *a,**k:{'held':False,'status':'LOST','error':'500','real_trading':False})
    monkeypatch.setattr(v10.runtime_lease,'acquire',lambda *a,**k:{'held':False,'status':'BLOCKED','error':'conflict','real_trading':False})
    monkeypatch.setattr(v12.base9.autonomous_paper.simulator,'set_enabled',lambda value:disabled.append(value))
    out=v12.resilient_heartbeat_runtime_lease()
    assert out['held'] is False
    assert out['reacquired'] is False
    assert disabled==[False]
    assert out['real_trading'] is False


def test_runtime_board_never_authorizes_live(monkeypatch):
    monkeypatch.setattr(v12.base9.autonomous_paper.simulator,'simulator_status',lambda:{'paper':{},'completed_cycles':0,'real_trading':False})
    monkeypatch.setattr(v12.base9.autonomous_paper,'milestones',lambda:{'elapsed_hours':0,'milestones':{},'real_trading':False})
    monkeypatch.setattr(v12,'_restore_state',lambda:{'status':'RESTORED_EXACT_PAPER_ENGINE','verified':True,'remote_state_hash':'a','local_state_hash':'a','backfill_used':False,'reconstructed':False,'real_trading':False})
    monkeypatch.setattr(v12,'_lease_local',lambda:{'held':True,'status':'HELD','real_trading':False})
    monkeypatch.setattr(v12.base11,'admission_status',lambda:{'status':'READY_EXACT_PAPER','session_id':'s','last_attempt_at':'2026-09-13T19:00:00+00:00','real_trading':False})
    monkeypatch.setattr(v12.tasks2130,'board',lambda **kwargs:{'tasks':[],'live_execution_allowed':False,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'real_trading':False})
    out=v12.runtime_board()
    assert out['real_trading'] is False
    assert out['live_execution_allowed'] is False
    assert out['automatic_promotion'] is False
    assert out['automatic_release'] is False
    assert out['setup_1_6_allowed'] is False
