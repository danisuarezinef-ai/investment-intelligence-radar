import json

import radar_autonomous_simulator_v1 as sim
from radar_experiment_brain_v1 import generate_experiments


def _state(**overrides):
    base={'active':True,'status':'ACTIVE','generation':3,'completed_cycles':4,
          'completed_experiments':12,'queued_experiments':0,'last_cycle_at':None,
          'last_research_at':None,'next_cycle_at':None,'next_research_at':None,
          'last_result':None,'last_error':None,'paper':{},'real_trading':False}
    base.update(overrides);return base


def test_experiments_keep_changing_across_generations():
    a=generate_experiments(1,count=12);b=generate_experiments(2,count=12)
    assert len(a)==12 and len(b)==12
    assert {json.dumps(x['configuration'],sort_keys=True) for x in a}.isdisjoint(
        {json.dumps(x['configuration'],sort_keys=True) for x in b})
    assert all(x['eligible_for_forward_promotion'] is False for x in a+b)
    assert all(x['real_trading'] is False for x in a+b)


def test_autonomous_cycle_runs_paper_research_and_audit(monkeypatch):
    writes=[];finished=[];persisted=[]
    monkeypatch.setattr(sim,'init_autonomous_simulator',lambda:None)
    monkeypatch.setattr(sim,'simulator_status',lambda:_state())
    monkeypatch.setattr(sim,'_set',lambda **kw:writes.append(kw))
    monkeypatch.setattr(sim,'_open_run',lambda generation:(77,'now'))
    monkeypatch.setattr(sim,'_finish_run',lambda run_id,**kw:finished.append((run_id,kw)))
    monkeypatch.setattr(sim,'_persist_experiments',lambda run_id,generation,research:persisted.append((run_id,generation,research)) or 6)
    monkeypatch.setattr(sim,'_ensure_paper_active',lambda initial_cash=1000:{'total':1000,'enabled':True})
    monkeypatch.setattr(sim,'run_simulator_cycle',lambda force=True:{'status':'OK','after':{'total':1005}})
    monkeypatch.setattr(sim,'run_research_batch',lambda generation:{'status':'COMPLETED','tested':6,'results':[{'experiment_id':'x'}]})
    r=sim.run_autonomous_cycle(force_research=True)
    assert r['status']=='ACTIVE' and r['result']['run_id']==77
    assert r['result']['paper_cycle_status']=='OK' and r['result']['experiments_tested']==6
    assert r['result']['experiment_results_persisted']==6
    assert persisted and persisted[0][0:2]==(77,3)
    assert finished and finished[0][1]['status']=='COMPLETED'
    assert any(w.get('generation')==4 and w.get('completed_experiments')==18 for w in writes)
    assert r['real_trading'] is False


def test_autonomous_cycle_respects_pause(monkeypatch):
    monkeypatch.setattr(sim,'init_autonomous_simulator',lambda:None)
    monkeypatch.setattr(sim,'simulator_status',lambda:_state(active=False,status='PAUSED'))
    assert sim.run_autonomous_cycle()['status']=='PAUSED'


def test_audit_schema_contains_restart_and_full_experiment_persistence():
    src=open(sim.__file__,encoding='utf-8').read()
    assert 'autonomous_simulator_runs' in src
    assert 'autonomous_experiment_results' in src
    assert 'INTERRUPTED_RESTART' in src
    assert 'result_json' in src and 'configuration' in src


def test_simulated_research_never_becomes_forward_evidence():
    src=open(sim.__file__,encoding='utf-8').read()
    assert "forward_evidence_mutated':False" in src
    assert "automatic_live_promotion':False" in src
    assert sim.REAL_TRADING is False
