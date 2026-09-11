import copy
from pathlib import Path

import pytest

import radar_core
import radar_agents
import radar_champion_portfolio as champion
import radar_paper_engine_persistence_v1 as persistence


def _use_tmp_db(monkeypatch,tmp_path):
    db=str(tmp_path/'paper_checkpoint.db')
    monkeypatch.setattr(radar_core,'DB',db)
    return db


def test_checkpoint_roundtrip_restores_exact_accounts_positions_trades_and_marks(monkeypatch,tmp_path):
    _use_tmp_db(monkeypatch,tmp_path)
    radar_agents.ensure_agents(reset=True,initial_cash=200)
    champion.reset_champion(200)
    c=radar_core.con()
    c.execute("update paper_agents set cash=111.25,last_rebalance='2026-09-11T01:00:00+00:00' where agent_id='aggressive'")
    c.execute("insert into paper_agent_positions(agent_id,symbol,qty,avg_price,updated_at) values('aggressive','NVDA',0.25,200,'2026-09-11T01:00:00+00:00')")
    c.execute("insert into paper_agent_trades(ts,agent_id,symbol,side,qty,price,gross_value,fees,spread_cost,fx_cost,reason) values('2026-09-11T01:00:00+00:00','aggressive','NVDA','BUY',0.25,200,50,0.1,0.1,0.05,'test')")
    c.execute("insert into paper_agent_marks(ts,agent_id,total,cash,invested,drawdown_pct) values('2026-09-11T01:01:00+00:00','aggressive',161.25,111.25,50,-1.2)")
    c.execute("update champion_paper_account set cash=150,last_step='2026-09-11T01:00:00+00:00' where id=1")
    c.execute("insert into champion_paper_positions(symbol,qty,avg_price,updated_at) values('MSFT',0.1,500,'2026-09-11T01:00:00+00:00')")
    c.execute("insert into champion_paper_marks(ts,total,cash,invested,drawdown_pct) values('2026-09-11T01:01:00+00:00',200,150,50,0)")
    c.commit();c.close()

    checkpoint=persistence.engine_checkpoint();expected_hash=checkpoint['state_hash']
    assert checkpoint['real_trading'] is False

    c=radar_core.con();c.execute("delete from paper_agent_positions");c.execute("update paper_agents set cash=200");c.execute("delete from champion_paper_positions");c.execute("update champion_paper_account set cash=200");c.commit();c.close()
    result=persistence.restore_engine_checkpoint(checkpoint)
    assert result['verified'] is True
    assert result['remote_state_hash']==expected_hash==result['local_state_hash']
    assert result['backfill_used'] is False and result['reconstructed'] is False
    assert result['real_trading'] is False

    c=radar_core.con()
    assert c.execute("select cash from paper_agents where agent_id='aggressive'").fetchone()[0]==111.25
    assert c.execute("select symbol,qty,avg_price from paper_agent_positions where agent_id='aggressive'").fetchone()==('NVDA',0.25,200.0)
    assert c.execute("select cash from champion_paper_account where id=1").fetchone()[0]==150.0
    assert c.execute("select symbol,qty,avg_price from champion_paper_positions").fetchone()==('MSFT',0.1,500.0)
    c.close()


def test_corrupt_checkpoint_fails_closed(monkeypatch,tmp_path):
    _use_tmp_db(monkeypatch,tmp_path);radar_agents.ensure_agents(reset=True,initial_cash=200);champion.reset_champion(200)
    checkpoint=persistence.engine_checkpoint();bad=copy.deepcopy(checkpoint);bad['tables']['paper_agents'][0]['cash']=999999
    with pytest.raises(ValueError,match='hash mismatch'):
        persistence.restore_engine_checkpoint(bad)


def test_checkpoint_endpoint_is_dedicated_and_private():
    source=Path('radar_paper_engine_persistence_v1.py').read_text(encoding='utf-8')
    edge=Path('supabase/functions/radar-paper-engine-checkpoint/index.ts').read_text(encoding='utf-8')
    migration=Path('supabase/migrations/20260910181500_paper_engine_checkpoint_v1.sql').read_text(encoding='utf-8').lower()
    cloud=Path('cloud_service_v3.py').read_text(encoding='utf-8')
    assert 'radar-paper-engine-checkpoint' in source
    assert 'persist_engine_checkpoint' in edge and 'rehydrate_engine_checkpoint' in edge
    assert 'enable row level security' in migration
    assert 'revoke all on table public.radar_paper_engine_checkpoints from public, anon, authenticated' in migration
    assert 'rehydrate_engine_checkpoint' in cloud and 'push_engine_checkpoint' in cloud
    assert "raise" in cloud
    assert persistence.REAL_TRADING is False
