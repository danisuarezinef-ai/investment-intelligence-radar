import radar_meta_decision_v2 as md


def test_calibration_shrinks_overconfidence_and_raises_gate(monkeypatch):
    monkeypatch.setattr(md,'calibration_profile',lambda **kw:{'scope':'agent','key':'champion','n':40,'hit_rate':.35,'mean_confidence':.85,'calibration_error':.50})
    conf,gate,ctx=md._calibrate(.90,.50,4.0,'1m','mixed')
    assert conf<.90
    assert gate>.50
    assert ctx['evidence']==1.0
    assert ctx['calibration_error']==.50


def test_small_memory_does_not_recalibrate(monkeypatch):
    monkeypatch.setattr(md,'calibration_profile',lambda **kw:{'scope':'agent','key':'champion','n':3,'hit_rate':0.0,'mean_confidence':1.0,'calibration_error':1.0})
    conf,gate,ctx=md._calibrate(.70,1.0,0.0,'1m','mixed')
    assert conf==.70
    assert ctx['evidence']==0.0
    assert gate==md.BASE_ABSTAIN_THRESHOLD


def test_drawdown_reduces_risk_budget(monkeypatch):
    monkeypatch.setattr(md,'champion_status',lambda:{'max_drawdown_pct':0.0})
    a,_=md._risk_budget(.8,.9,{'evidence':0.0,'calibration_error':0.0})
    monkeypatch.setattr(md,'champion_status',lambda:{'max_drawdown_pct':12.0})
    b,ctx=md._risk_budget(.8,.9,{'evidence':0.0,'calibration_error':0.0})
    assert b<a
    assert ctx['drawdown_factor']<1.0


def test_multi_horizon_shadow_never_enables_real_trading(monkeypatch):
    monkeypatch.setattr(md,'champion_decision',lambda limit=8,horizon='1m',record=True:{'horizon':horizon,'real_trading':False})
    out=md.multi_horizon_shadow_decisions(('1d','1w','3m'))
    assert set(out)=={'1d','1w','3m'}
    assert all(v['real_trading'] is False for v in out.values())
