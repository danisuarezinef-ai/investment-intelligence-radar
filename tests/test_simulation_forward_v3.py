import json
import radar_core
import radar_agents
import radar_simulation_forward_v3 as sf
import radar_decision_memory_v2 as dm
import radar_memory_outcomes_v4 as mo


def _tmp(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'))
    monkeypatch.setattr(radar_core,'STATUS',str(tmp_path/'status.json'))
    monkeypatch.setattr(radar_core,'LOG',str(tmp_path/'worker.log'))
    monkeypatch.setattr(radar_core,'PID',str(tmp_path/'worker.pid'))
    radar_core.init_db(); radar_agents.ensure_agents(reset=True,initial_cash=200); sf.init_forward_v3_db(); dm.init_decision_memory_db()


def test_forward_trade_import_is_idempotent_and_benchmark_is_recorded(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch)
    prices={'MSFT':100.0,'NVDA':50.0}
    monkeypatch.setattr(sf,'_latest_prices',lambda:prices)
    monkeypatch.setattr(radar_core,'_latest_prices',lambda:prices)
    c=radar_core.con()
    c.execute("insert into paper_agent_trades(ts,agent_id,symbol,side,qty,price,gross_value,fees,spread_cost,fx_cost,reason) values(?,?,?,?,?,?,?,?,?,?,?)",('2026-01-01T10:00:00+00:00','conservative','MSFT','BUY',1,100,100,.1,.1,.05,'test'))
    c.commit(); c.close()
    first=sf.capture_forward_mark_v3(); second=sf.capture_forward_mark_v3()
    c=radar_core.con()
    n=c.execute("select count(*) from simulation_ledger where run_id='forward-live' and event_type='BUY'").fetchone()[0]
    b=c.execute("select benchmark from simulation_marks where run_id='forward-live' and benchmark is not null limit 1").fetchone()[0]
    c.close()
    assert n==1
    assert b>0
    assert first['forward_v3']['trades_imported_this_cycle']==1
    assert second['forward_v3']['trades_imported_this_cycle']==0
    assert second['forward_v3']['benchmark_value']>0


def test_abstain_episode_learns_avoided_loss(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch)
    eid=dm.record_episode(agent_id='champion',symbol=None,horizon='1d',regime='mixed',state={},evidence={},hypothesis={'top':{'symbol':'MSFT'}},action='ABSTAIN',confidence=.7,tags=['champion'])
    c=radar_core.con()
    c.execute("insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)",('2026-01-01T10:00:00+00:00','MSFT',100,None,'test'))
    c.execute("insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)",('2026-01-02T10:00:00+00:00','MSFT',90,None,'test'))
    c.commit(); c.close()
    out=mo.evaluate_mature_episodes_v4()
    c=radar_core.con(); raw=c.execute('select outcome from decision_episodes where episode_id=?',(eid,)).fetchone()[0]; c.close(); outcome=json.loads(raw)
    assert out['evaluated']==1
    assert out['abstain_evaluated']==1
    assert outcome['reference_symbol']=='MSFT'
    assert outcome['hit'] is True
    assert outcome['reward']>0
    assert outcome['return_pct']<0


def test_abstain_penalizes_material_missed_gain(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch)
    eid=dm.record_episode(agent_id='champion',symbol=None,horizon='1d',regime='mixed',state={'x':1},evidence={},hypothesis={'top':{'symbol':'MSFT'}},action='ABSTAIN',confidence=.7,tags=['champion'])
    c=radar_core.con()
    c.execute("insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)",('2026-01-01T10:00:00+00:00','MSFT',100,None,'test'))
    c.execute("insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)",('2026-01-02T10:00:00+00:00','MSFT',110,None,'test'))
    c.commit(); c.close()
    mo.evaluate_mature_episodes_v4()
    c=radar_core.con(); outcome=json.loads(c.execute('select outcome from decision_episodes where episode_id=?',(eid,)).fetchone()[0]); c.close()
    assert outcome['hit'] is False
    assert outcome['reward']<0
