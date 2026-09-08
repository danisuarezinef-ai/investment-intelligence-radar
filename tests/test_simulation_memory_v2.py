import json
from datetime import date,timedelta

import radar_core
from radar_decision_memory_v2 import record_episode,evaluate_episode,retrieve_similar,memory_health
from radar_simulation_v2 import _metrics,replay_historical
from radar_learning_v2 import update_agent_skill,agent_skill_table


def _tmp_db(monkeypatch,tmp_path):
    db=tmp_path/'radar_test.db'; monkeypatch.setattr(radar_core,'DB',str(db)); return db


def test_metrics_include_downside_and_benchmark():
    m=_metrics([100,105,102,110],[100,102,104,106])
    assert m['marks']==4
    assert m['return_pct']>0
    assert m['max_drawdown_pct']<0
    assert m['benchmark_return_pct']>0
    assert m['alpha_pct'] is not None


def test_episode_is_single_assignment_and_retrievable(monkeypatch,tmp_path):
    _tmp_db(monkeypatch,tmp_path)
    eid=record_episode(agent_id='champion',symbol='MSFT',horizon='1m',regime='risk_on',state={'x':1},evidence={'source':'test'},hypothesis={'up':True},action='PAPER_BUY_CANDIDATE',confidence=.7,tags=['champion','test'])
    evaluate_episode(eid,{'alpha_pct':3.0},lesson='worked')
    rows=retrieve_similar(symbol='MSFT',horizon='1m',tags=['champion'])
    assert rows and rows[0]['episode_id']==eid
    assert memory_health()['evaluated']==1
    try:
        evaluate_episode(eid,{'alpha_pct':4.0})
        assert False,'second outcome assignment must fail'
    except ValueError:
        pass


def test_pit_historical_replay_and_agent_skill(monkeypatch,tmp_path):
    _tmp_db(monkeypatch,tmp_path); radar_core.init_db(); c=radar_core.con()
    start=date(2026,1,1)
    symbols=['MSFT','NVDA','GOOGL','AMZN','META']
    for i in range(80):
        d=(start+timedelta(days=i)).isoformat()+'T21:00:00+00:00'
        for j,s in enumerate(symbols):
            price=100+j*10+i*(0.45+0.05*j)
            c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',(d,s,price,1000+i,'fixture Historical'))
    c.commit();c.close()
    out=replay_historical(initial_cash=200.0,run_id='test-hist')
    assert out['configured'] is True
    assert out['mode']=='historical'
    assert len(out['agents'])==5
    assert out['real_trading'] is False
    assert all(a['marks']>0 for a in out['agents'])
    n=update_agent_skill(regime='fixture',horizon='historical')
    assert n>0
    skills=agent_skill_table()
    assert skills and skills[0]['n']>0
