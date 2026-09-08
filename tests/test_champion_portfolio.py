import radar_core
import radar_champion_portfolio as cp


def _tmp(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'))
    monkeypatch.setattr(radar_core,'STATUS',str(tmp_path/'status.json'))
    monkeypatch.setattr(radar_core,'LOG',str(tmp_path/'worker.log'))
    monkeypatch.setattr(radar_core,'PID',str(tmp_path/'worker.pid'))
    radar_core.init_db(); cp.init_champion_db(); cp.reset_champion(200)


def test_champion_executes_only_paper_buy(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch); monkeypatch.setattr(cp,'_latest_prices',lambda:{'MSFT':100.0})
    d={'action':'PAPER_BUY_CANDIDATE','symbol':'MSFT','confidence':.8,'allocation_fraction':.10,'candidates':[{'symbol':'MSFT','champion_score':5}]}
    st=cp.step_champion(d)
    assert st['real_trading'] is False
    assert st['cash']<200
    assert len(st['positions'])==1
    assert st['positions'][0]['symbol']=='MSFT'
    assert st['trades'][0]['side']=='BUY'


def test_champion_abstain_does_not_open_position(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch); monkeypatch.setattr(cp,'_latest_prices',lambda:{'MSFT':100.0})
    st=cp.step_champion({'action':'ABSTAIN','symbol':None,'confidence':.2,'candidates':[]})
    assert st['cash']==200
    assert st['positions']==[]


def test_champion_stop_loss_closes_position(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch); prices={'MSFT':100.0}; monkeypatch.setattr(cp,'_latest_prices',lambda:prices)
    cp.step_champion({'action':'PAPER_BUY_CANDIDATE','symbol':'MSFT','confidence':.8,'allocation_fraction':.10,'candidates':[{'symbol':'MSFT','champion_score':5}]})
    prices['MSFT']=80.0
    st=cp.step_champion({'action':'ABSTAIN','symbol':None,'confidence':.2,'candidates':[]})
    assert st['positions']==[]
    assert st['trades'][0]['side']=='SELL'
