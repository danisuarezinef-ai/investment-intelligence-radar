import radar_core
import radar_learning
import radar_causal_scoring_v2 as cs
import radar_meta_decision_v2 as md


def _tmp(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'))
    monkeypatch.setattr(radar_core,'STATUS',str(tmp_path/'status.json'))
    monkeypatch.setattr(radar_core,'LOG',str(tmp_path/'worker.log'))
    monkeypatch.setattr(radar_core,'PID',str(tmp_path/'worker.pid'))
    radar_core.init_db();radar_learning.init_learning_db()


def test_negative_supply_chain_evidence_reduces_score(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);c=radar_core.con()
    c.execute("insert into causal_edges(created_at,source_node,relation,target_node,depth,confidence,evidence_event_id,horizon,metadata) values(?,?,?,?,?,?,?,?,?)",('2026','TRADE_CONTROLS','supply_chain_risk','TSM',1,.9,1,'medium','{}'))
    c.commit();c.close();out=cs.causal_symbol_score('TSM','1m')
    assert out['available'] is True
    assert out['score']<0
    assert out['adjustment']<0
    assert out['negative_events']==1
    assert out['real_trading'] is False


def test_one_event_counts_once_despite_edge_fanout(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);c=radar_core.con()
    for rel,conf in [('direct_signal',.6),('raises_demand_for',.9),('sector_tailwind',.5)]:
        c.execute("insert into causal_edges(created_at,source_node,relation,target_node,depth,confidence,evidence_event_id,horizon,metadata) values(?,?,?,?,?,?,?,?,?)",('2026','AI_COMPUTE',rel,'NVDA',1,conf,77,'medium','{}'))
    c.commit();c.close();out=cs.causal_symbol_score('NVDA','1m')
    assert out['independent_events']==1
    assert len(out['evidence'])==1
    assert out['adjustment']>0


def test_champion_candidate_exposes_causal_audit(monkeypatch):
    monkeypatch.setattr(md,'detect_regime',lambda store=False:{'regime':'mixed','confidence':.8})
    monkeypatch.setattr(md,'opportunity_rankings',lambda n:{'bajo':[{'symbol':'MSFT','score':4.0,'risk':'bajo','volatility':10.0}],'intermedio':[],'alto':[]})
    monkeypatch.setattr(md,'agents_status',lambda:[{'configured':True,'agent_id':aid,'sharpe':0,'max_drawdown_pct':0,'pnl_pct':0} for aid in md.AGENTS])
    monkeypatch.setattr(md,'agent_skill_table',lambda limit=200:[])
    monkeypatch.setattr(md,'_memory_adjust',lambda symbol,regime,horizon:(0.0,0,{'source':'test'}))
    monkeypatch.setattr(md,'causal_symbol_score',lambda symbol,horizon:{'available':True,'adjustment':1.25,'confidence':.8,'independent_events':3,'real_trading':False})
    monkeypatch.setattr(md,'calibration_profile',lambda **kw:{'n':0,'hit_rate':None,'calibration_error':None})
    monkeypatch.setattr(md,'champion_status',lambda:{'max_drawdown_pct':0})
    out=md.champion_decision(record=False)
    top=out['candidates'][0]
    assert top['causal_adjustment']==1.25
    assert top['causal_context']['independent_events']==3
    assert out['real_trading'] is False
