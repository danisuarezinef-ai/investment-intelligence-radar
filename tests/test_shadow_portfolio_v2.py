import os, sqlite3, tempfile
import radar_core
import radar_shadow_portfolio_v2 as sp


def _db(monkeypatch):
    td=tempfile.TemporaryDirectory(); path=os.path.join(td.name,'radar.db')
    def con():
        c=sqlite3.connect(path); c.execute('pragma journal_mode=wal'); return c
    monkeypatch.setattr(radar_core,'con',con); monkeypatch.setattr(sp,'con',con)
    radar_core.init_db(); return td,con


def test_start_requires_all_release_gates(monkeypatch):
    td,con=_db(monkeypatch)
    r=sp.start_shadow_portfolio_v2({'forward_ledger':True})
    assert r['started'] is False and 'oos_audit' in r['missing'] and r['real_trading'] is False
    td.cleanup()


def test_shadow_decisions_are_immutable_and_marks_require_future_price(monkeypatch):
    td,con=_db(monkeypatch)
    gates={k:True for k in ('forward_ledger','oos_audit','allocation_engine','risk_engine','ci')}
    monkeypatch.setattr(sp,'now',lambda:'2026-09-09T01:00:00+00:00')
    assert sp.start_shadow_portfolio_v2(gates)['started'] is True
    c=con(); c.execute("insert into market_snapshots(ts,symbol,price,volume,source) values('2026-09-09T00:00:00+00:00','AAA',100,1000,'test')"); c.commit(); c.close()
    cards=[{'symbol':'AAA','horizon':'1m','action':'BUY','evidence_complete':True,'expected_return_pct':12,'downside_pct':-2,'confidence':.8,'valuation_risk':1}]
    portfolio={'total':1000,'invested':0,'cash':1000,'max_drawdown_pct':0,'positions':[]}
    meta={'AAA':{'sector':'tech','geography':'US','fx':'USD','liquidity_score':1}}
    r=sp.capture_shadow_plan(portfolio=portfolio,metadata_by_symbol=meta,correlations={},cards=cards)
    assert r['captured']==1
    c=con(); did=c.execute('select id from shadow_portfolio_decisions_v2').fetchone()[0]
    try:
        c.execute("update shadow_portfolio_decisions_v2 set approved_budget=1 where id=?",(did,)); c.commit(); assert False
    except sqlite3.DatabaseError: c.rollback()
    c.close()
    assert sp.mark_shadow_portfolio_v2()['pending_market_data']==1
    c=con(); c.execute("insert into market_snapshots(ts,symbol,price,volume,source) values('2026-09-09T02:00:00+00:00','AAA',110,1000,'test')"); c.commit(); c.close()
    out=sp.mark_shadow_portfolio_v2(); assert out['marked']==1
    status=sp.shadow_portfolio_v2_status(); assert status['decisions']==1 and status['marks']==1
    assert round(status['positions'][0]['return_pct'],6)==10.0 and status['real_trading'] is False
    td.cleanup()


def test_status_never_claims_verified_performance(monkeypatch):
    td,con=_db(monkeypatch)
    s=sp.shadow_portfolio_v2_status()
    assert 'NOT VERIFIED' in s['performance_claim'] and s['can_trade'] is False
    td.cleanup()
