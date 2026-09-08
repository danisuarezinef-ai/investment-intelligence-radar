import radar_core
import radar_decision_memory_v2 as dm
import radar_memory_outcomes_v3 as mo
import radar_simulation_v2 as sim
import radar_learning_v2 as lv2


def _tmp(tmp_path, monkeypatch):
    db=str(tmp_path/'radar.db')
    monkeypatch.setattr(radar_core,'DB',db)
    monkeypatch.setattr(radar_core,'STATUS',str(tmp_path/'status.json'))
    monkeypatch.setattr(radar_core,'LOG',str(tmp_path/'worker.log'))
    monkeypatch.setattr(radar_core,'PID',str(tmp_path/'worker.pid'))
    radar_core.init_db(); dm.init_decision_memory_db(); sim.init_simulation_db(); lv2.init_learning_v2_db()
    return db


def test_mature_episode_gets_forward_market_outcome_once(tmp_path, monkeypatch):
    _tmp(tmp_path,monkeypatch)
    monkeypatch.setattr(dm,'now',lambda:'2026-01-01T10:00:00+00:00')
    eid=dm.record_episode(agent_id='champion',symbol='MSFT',horizon='1m',regime='test',state={},evidence={'lookahead':False},action='PAPER_BUY_CANDIDATE',confidence=.7,tags=['champion'])
    c=radar_core.con()
    for i in range(22):
        c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',(f'2026-01-{i+1:02d}T21:00:00+00:00','MSFT',100+i,None,'TEST'))
    c.commit();c.close()
    out=mo.evaluate_mature_episodes()
    assert out['evaluated']==1
    c=radar_core.con(); row=c.execute('select outcome from decision_episodes where episode_id=?',(eid,)).fetchone(); c.close()
    assert row and row[0] is not None
    again=mo.evaluate_mature_episodes()
    assert again['evaluated']==0


def test_agent_skill_never_crosses_simulation_run_boundary(tmp_path, monkeypatch):
    _tmp(tmp_path,monkeypatch)
    c=radar_core.con()
    for run_id,vals in [('r1',[100,110]),('r2',[1000,900])]:
        for i,total in enumerate(vals):
            c.execute('insert into simulation_marks(run_id,ts,agent_id,total,cash,invested,benchmark,drawdown_pct) values(?,?,?,?,?,?,?,?)',(run_id,f'2026-01-0{i+1}','balanced',total,total,0,None,0))
    c.commit();c.close()
    assert lv2.update_agent_skill()==1
    row=next(x for x in lv2.agent_skill_table() if x['agent_id']=='balanced')
    assert row['n']==2
    assert abs(row['mean_alpha'])<1e-9
