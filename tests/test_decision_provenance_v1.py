import copy
import json

import pytest

import radar_core
import radar_agents
import radar_champion_portfolio as champion
import radar_decision_provenance_v1 as provenance
import radar_paper_engine_persistence_v1 as persistence
import radar_pre160_runtime_v5 as runtime_v5


def _use_tmp_db(monkeypatch,tmp_path):
    db=str(tmp_path/'decision_provenance.db')
    monkeypatch.setattr(radar_core,'DB',db)
    return db


def _seed_pit(c):
    c.execute("insert into market_snapshots(ts,symbol,price,volume,source) values('2026-09-12T10:00:00+00:00','MSFT',100,1,'BEFORE_PROVIDER')")
    c.execute("insert into market_snapshots(ts,symbol,price,volume,source) values('2026-09-12T12:00:00+00:00','MSFT',999,1,'AFTER_PROVIDER')")
    c.execute("create table if not exists market_regimes(id integer primary key,ts text,regime text,confidence real,features text)")
    c.execute("insert into market_regimes(ts,regime,confidence,features) values('2026-09-12T09:30:00+00:00','RISK_ON',0.7,'{\"vol\":1}')")
    c.execute("insert into market_regimes(ts,regime,confidence,features) values('2026-09-12T12:30:00+00:00','FUTURE_REGIME',0.99,'{}')")
    c.execute("create table if not exists model_versions(version text primary key,created_at text)")
    c.execute("insert into model_versions(version,created_at) values('model-before','2026-09-12T09:00:00+00:00')")
    c.execute("insert into model_versions(version,created_at) values('model-after','2026-09-12T13:00:00+00:00')")


def test_strategy_version_is_content_addressed_and_deterministic():
    a=provenance.strategy_version('paper_agent:balanced',{'target':0.7,'max_positions':5})
    b=provenance.strategy_version('paper_agent:balanced',{'max_positions':5,'target':0.70})
    c=provenance.strategy_version('paper_agent:balanced',{'target':0.8,'max_positions':5})
    assert a==b
    assert a.startswith('cfgsha256:') and len(a)==74
    assert c!=a


def test_capture_uses_only_point_in_time_data_and_is_immutable(monkeypatch,tmp_path):
    _use_tmp_db(monkeypatch,tmp_path);radar_core.init_db();c=radar_core.con();_seed_pit(c);provenance.init_decision_provenance_db(c)
    trade_ts='2026-09-12T11:00:00+00:00'
    env=provenance.capture_trade_envelope(c,source_key='agent:balanced',trade_id=1,trade_ts=trade_ts,competitor_key='balanced',
        strategy_identity='paper_agent:balanced',strategy_config={'target':.7},symbol='MSFT',side='BUY',
        cost_snapshot={'fees':.1,'spread_cost':.2,'fx_cost':.05,'total':.35},decision_payload={'score':3.2})
    c.commit()
    assert env['provider_snapshot']['source']=='BEFORE_PROVIDER'
    assert env['provider_snapshot']['price']==100.0
    assert env['regime']=='RISK_ON'
    assert env['provenance']['decision_model_version']=='model-before'
    assert env['provenance']['lookahead'] is False
    assert env['provenance']['backfilled'] is False
    assert env['provenance']['reconstructed'] is False
    assert env['benchmark_snapshot']['constituents']['MSFT']['price']==100.0
    assert env['benchmark_snapshot']['constituents']['MSFT']['source']=='BEFORE_PROVIDER'
    again=provenance.capture_trade_envelope(c,source_key='agent:balanced',trade_id=1,trade_ts=trade_ts,competitor_key='balanced',
        strategy_identity='paper_agent:balanced',strategy_config={'target':.7},symbol='MSFT',side='BUY',
        cost_snapshot={'fees':.1,'spread_cost':.2,'fx_cost':.05,'total':.35},decision_payload={'score':3.2})
    assert again['envelope_hash']==env['envelope_hash']
    with pytest.raises(RuntimeError,match='immutable decision envelope collision'):
        provenance.capture_trade_envelope(c,source_key='agent:balanced',trade_id=1,trade_ts=trade_ts,competitor_key='balanced',
            strategy_identity='paper_agent:balanced',strategy_config={'target':.7},symbol='MSFT',side='BUY',
            cost_snapshot={'fees':.1,'spread_cost':.2,'fx_cost':.05,'total':.35},decision_payload={'score':99})
    c.close()


def test_agent_buy_captures_transactional_provenance(monkeypatch,tmp_path):
    _use_tmp_db(monkeypatch,tmp_path)
    monkeypatch.setattr(radar_agents,'history_ready',lambda:True)
    monkeypatch.setattr(radar_agents,'_latest_prices',lambda:{'MSFT':100.0})
    rankings={'bajo':[{'symbol':'MSFT','score':4.0,'risk':'bajo','volatility':12.0}],'intermedio':[],'alto':[]}
    monkeypatch.setattr(radar_agents,'opportunity_rankings',lambda *a,**k:rankings)
    radar_agents.ensure_agents(reset=True,initial_cash=200)
    result=radar_agents.step_agent('balanced',force=True)
    rows=provenance.load_local_envelopes()
    buys=[x for x in rows if x['competitor_key']=='balanced' and x['side']=='BUY']
    assert result['positions'] and len(buys)==1
    env=buys[0]
    assert env['strategy_version'].startswith('cfgsha256:')
    assert env['provenance']['capture_mode']=='AT_DECISION_TRANSACTION'
    assert env['provenance']['strategy_version_status']=='CAPTURED_AT_DECISION'
    assert env['provenance']['lookahead'] is False
    assert env['cost_snapshot']['fees']>0 and env['cost_snapshot']['spread_cost']>0 and env['cost_snapshot']['fx_cost']>0
    assert env['real_trading'] is False


def test_champion_buy_captures_transactional_provenance(monkeypatch,tmp_path):
    _use_tmp_db(monkeypatch,tmp_path)
    champion.reset_champion(200)
    monkeypatch.setattr(champion,'_latest_prices',lambda:{'MSFT':100.0})
    monkeypatch.setattr(champion,'portfolio_risk_gate',lambda *a,**k:{'allowed_budget':40.0,'risk_multiplier':0.8,'allowed':True})
    decision={'action':'PAPER_BUY_CANDIDATE','symbol':'MSFT','confidence':0.75,'allocation_fraction':0.2,
              'candidates':[{'symbol':'MSFT','champion_score':2.0}]}
    result=champion.step_champion(decision)
    rows=provenance.load_local_envelopes();buys=[x for x in rows if x['competitor_key']=='champion' and x['side']=='BUY']
    assert result['positions'] and len(buys)==1
    env=buys[0]
    assert env['strategy_identity']=='champion_paper'
    assert env['strategy_version'].startswith('cfgsha256:')
    assert env['provenance']['capture_mode']=='AT_DECISION_TRANSACTION'
    assert env['decision_payload']['risk_multiplier']==0.8
    assert env['real_trading'] is False


def test_closed_outcome_linkage_never_uses_exit_fields():
    env={'competitor_key':'balanced','symbol':'MSFT','trade_ts':'2026-09-12T11:00:00+00:00','side':'BUY','envelope_hash':'abc',
         'strategy_version':'cfgsha256:'+'a'*64,'provenance':{'capture_mode':'AT_DECISION_TRANSACTION','lookahead':False}}
    decision={'competitor_key':'balanced','symbol':'MSFT','entry_ts':'2026-09-12T11:00:00+00:00','exit_ts':'2026-09-13T11:00:00+00:00',
              'decision_fingerprint':'closed-fingerprint-one','forward_eligible':True,'evidence_class':'PROSPECTIVE_PAPER_CLOSE','realized_pnl':1.0}
    first=runtime_v5.decision_trace_linkage([decision],[env])
    changed=dict(decision,exit_ts='2026-10-01T00:00:00+00:00',decision_fingerprint='totally-different-closed-fingerprint')
    second=runtime_v5.decision_trace_linkage([changed],[env])
    assert first['matched']==second['matched']==1
    assert first['uses_exit_fields_for_entry_linkage'] is False
    assert second['uses_exit_fields_for_entry_linkage'] is False
    assert first['rows'][0]['entry_envelope_hash']==second['rows'][0]['entry_envelope_hash']=='abc'


def test_schema2_checkpoint_roundtrip_includes_provenance(monkeypatch,tmp_path):
    _use_tmp_db(monkeypatch,tmp_path);radar_agents.ensure_agents(reset=True,initial_cash=200);champion.reset_champion(200)
    c=radar_core.con();trade_ts='2026-09-12T11:00:00+00:00'
    c.execute("insert into paper_agent_trades(ts,agent_id,symbol,side,qty,price,gross_value,fees,spread_cost,fx_cost,reason) values(?,?,?,?,?,?,?,?,?,?,?)",
              (trade_ts,'balanced','MSFT','BUY',.2,100,20,.02,.02,.01,'test'))
    trade_id=c.execute('select max(id) from paper_agent_trades').fetchone()[0]
    provenance.capture_trade_envelope(c,source_key='agent:balanced',trade_id=trade_id,trade_ts=trade_ts,competitor_key='balanced',
        strategy_identity='paper_agent:balanced',strategy_config={'target':.7},symbol='MSFT',side='BUY',
        cost_snapshot={'fees':.02,'spread_cost':.02,'fx_cost':.01,'total':.05},decision_payload={'score':2})
    c.commit();c.close()
    cp=persistence.engine_checkpoint();assert cp['schema_version']==2;assert len(cp['tables']['paper_decision_envelopes_local'])==1
    expected=cp['state_hash'];c=radar_core.con();c.execute('delete from paper_decision_envelopes_local');c.commit();c.close()
    restored=persistence.restore_engine_checkpoint(cp)
    assert restored['verified'] is True and restored['remote_state_hash']==expected==restored['local_state_hash']
    assert restored['remote_schema_version']==2 and restored['schema_migrated'] is False
    assert len(provenance.load_local_envelopes())==1


def test_legacy_schema1_checkpoint_restores_and_migrates_without_fabricating_provenance(monkeypatch,tmp_path):
    _use_tmp_db(monkeypatch,tmp_path);radar_agents.ensure_agents(reset=True,initial_cash=200);champion.reset_champion(200)
    cp2=persistence.engine_checkpoint();legacy=copy.deepcopy(cp2);legacy['schema_version']=1;legacy['tables'].pop('paper_decision_envelopes_local');legacy['state_hash']=persistence.state_hash(legacy['tables'])
    result=persistence.restore_engine_checkpoint(legacy)
    assert result['verified'] is True
    assert result['remote_schema_version']==1 and result['local_schema_version']==2 and result['schema_migrated'] is True
    assert result['backfill_used'] is False and result['reconstructed'] is False
    assert provenance.load_local_envelopes()==[]
    assert result['real_trading'] is False
