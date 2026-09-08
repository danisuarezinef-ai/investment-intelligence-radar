import radar_meta_decision_v2 as md


def _status(agent_id='balanced'):
    return {'configured':True,'agent_id':agent_id,'sharpe':0.0,'max_drawdown_pct':0.0,'pnl_pct':0.0}


def test_learned_skill_changes_agent_weight(monkeypatch):
    monkeypatch.setattr(md,'agent_skill_table',lambda limit=200:[{'agent_id':'balanced','regime':'risk_off','horizon':'forward','n':40,'score':3.0}])
    learned,ctx=md._agent_quality(_status(),'risk_off')
    monkeypatch.setattr(md,'agent_skill_table',lambda limit=200:[])
    plain,_=md._agent_quality(_status(),'risk_off')
    assert learned>plain
    assert ctx['source']=='paper+learned_skill'
    assert ctx['n']==40


def test_champion_records_detected_regime(monkeypatch):
    monkeypatch.setattr(md,'detect_regime',lambda store=False:{'regime':'risk_on_growth','confidence':.8,'features':{}})
    monkeypatch.setattr(md,'opportunity_rankings',lambda n:{'bajo':[{'symbol':'MSFT','score':5.0,'risk':'bajo','volatility':10.0}],'intermedio':[],'alto':[]})
    monkeypatch.setattr(md,'agents_status',lambda:[_status(aid) for aid in md.AGENTS])
    monkeypatch.setattr(md,'agent_skill_table',lambda limit=200:[])
    monkeypatch.setattr(md,'retrieve_similar',lambda **kw:[])
    out=md.champion_decision(record=False)
    assert out['regime']=='risk_on_growth'
    assert out['regime_confidence']==.8
    assert out['real_trading'] is False
    assert set(out['agent_skill_context'])==set(md.AGENTS)
