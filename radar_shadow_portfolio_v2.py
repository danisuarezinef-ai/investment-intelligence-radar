"""Prospective Shadow Portfolio v2.

Records immutable, risk-gated target allocations and marks them using only
market snapshots observed after the shadow decision. No backfill and no real
execution capability.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from radar_core import con, now
from radar_decision_allocation_v1 import integrated_portfolio_plan

REAL_TRADING = False
CONTROL_KEY = 'shadow_portfolio_v2_started_at'


def _dt(x):
    if not x: return None
    try: return datetime.fromisoformat(str(x).replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception: return None


def _canon(x): return json.dumps(x, sort_keys=True, separators=(',',':'), default=str)
def _digest(x): return hashlib.sha256(_canon(x).encode()).hexdigest()


def init_shadow_portfolio(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS shadow_portfolio_decisions_v2(
      id TEXT PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL,
      action TEXT NOT NULL, requested_budget REAL NOT NULL, approved_budget REAL NOT NULL,
      target_fraction REAL NOT NULL, entry_price REAL NOT NULL, entry_price_ts TEXT NOT NULL,
      decision_payload TEXT NOT NULL, decision_hash TEXT NOT NULL UNIQUE,
      real_trading INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS shadow_portfolio_marks_v2(
      id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id TEXT NOT NULL, marked_at TEXT NOT NULL,
      price REAL NOT NULL, price_ts TEXT NOT NULL, return_pct REAL NOT NULL,
      FOREIGN KEY(decision_id) REFERENCES shadow_portfolio_decisions_v2(id));
    CREATE UNIQUE INDEX IF NOT EXISTS idx_shadow_mark_v2 ON shadow_portfolio_marks_v2(decision_id,price_ts);
    CREATE TRIGGER IF NOT EXISTS shadow_decision_v2_no_update BEFORE UPDATE ON shadow_portfolio_decisions_v2
      BEGIN SELECT RAISE(ABORT,'shadow decision is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS shadow_decision_v2_no_delete BEFORE DELETE ON shadow_portfolio_decisions_v2
      BEGIN SELECT RAISE(ABORT,'shadow decision is immutable'); END;
    CREATE TRIGGER IF NOT EXISTS shadow_mark_v2_no_update BEFORE UPDATE ON shadow_portfolio_marks_v2
      BEGIN SELECT RAISE(ABORT,'shadow mark is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS shadow_mark_v2_no_delete BEFORE DELETE ON shadow_portfolio_marks_v2
      BEGIN SELECT RAISE(ABORT,'shadow mark is append-only'); END;
    ''')
    db.commit()


def start_shadow_portfolio_v2(release_gates):
    required=('forward_ledger','oos_audit','allocation_engine','risk_engine','ci')
    if not all((release_gates or {}).get(k) is True for k in required):
        return {'started':False,'reason':'release_gates_not_verified','missing':[k for k in required if (release_gates or {}).get(k) is not True],'real_trading':False}
    c=con(); init_shadow_portfolio(c)
    row=c.execute('select value from control where key=?',(CONTROL_KEY,)).fetchone()
    if row: stamp=row[0]
    else:
        stamp=now(); c.execute('insert into control(key,value) values(?,?)',(CONTROL_KEY,stamp)); c.commit()
    c.close(); return {'started':True,'started_at':stamp,'real_trading':False}


def _boundary(c):
    row=c.execute('select value from control where key=?',(CONTROL_KEY,)).fetchone()
    return row[0] if row else None


def _latest_price_at_or_before(c,symbol,cutoff):
    return c.execute('select price,ts from market_snapshots where symbol=? and ts<=? order by ts desc,id desc limit 1',(symbol,cutoff)).fetchone()


def capture_shadow_plan(*, portfolio, metadata_by_symbol, correlations, cards=None,
                        allocation_policy=None, risk_limits=None):
    """Freeze approved target allocations using evidence available at call time."""
    c=con(); init_shadow_portfolio(c); boundary=_boundary(c)
    if not boundary:
        c.close(); return {'captured':0,'reason':'not_started','real_trading':False}
    stamp=now()
    plan=integrated_portfolio_plan(portfolio=portfolio,metadata_by_symbol=metadata_by_symbol,
        correlations=correlations,cards=cards,allocation_policy=allocation_policy,risk_limits=risk_limits)
    captured=[]; errors=[]
    for row in plan.get('approved') or []:
        symbol=str(row.get('symbol') or '')
        px=_latest_price_at_or_before(c,symbol,stamp)
        if not px:
            errors.append({'symbol':symbol,'error':'entry_price_missing_at_decision_boundary'}); continue
        payload={'created_at':stamp,'symbol':symbol,'action':row.get('action'),'requested_budget':row.get('requested_budget'),
                 'approved_budget':row.get('approved_budget'),'target_fraction':row.get('target_fraction'),
                 'confidence':row.get('confidence'),'expected_return_pct':row.get('expected_return_pct'),
                 'downside_pct':row.get('downside_pct'),'risk':row.get('risk'),
                 'pipeline':plan.get('pipeline'),'immutable':True,'backfilled':False,'real_trading':False}
        h=_digest(payload); did=h[:24]
        try:
            c.execute('''insert into shadow_portfolio_decisions_v2
              (id,created_at,symbol,action,requested_budget,approved_budget,target_fraction,entry_price,entry_price_ts,decision_payload,decision_hash,real_trading)
              values(?,?,?,?,?,?,?,?,?,?,?,0)''',(did,stamp,symbol,row.get('action'),float(row.get('requested_budget') or 0),float(row.get('approved_budget') or 0),float(row.get('target_fraction') or 0),float(px[0]),px[1],_canon(payload),h))
            captured.append(did)
        except Exception as exc: errors.append({'symbol':symbol,'error':str(exc)})
    c.commit(); c.close()
    return {'captured':len(captured),'decision_ids':captured,'errors':errors,'approved_count':plan.get('approved_count',0),'rejected_count':plan.get('rejected_count',0),'real_trading':False}


def mark_shadow_portfolio_v2():
    """Append one mark per decision using only prices timestamped after decision."""
    c=con(); init_shadow_portfolio(c); boundary=_boundary(c)
    if not boundary:
        c.close(); return {'marked':0,'reason':'not_started','real_trading':False}
    rows=c.execute('select id,created_at,symbol,entry_price from shadow_portfolio_decisions_v2 order by created_at,id').fetchall()
    marked=0; pending=0
    for did,created,symbol,entry in rows:
        price=c.execute('select price,ts from market_snapshots where symbol=? and ts>? order by ts desc,id desc limit 1',(symbol,created)).fetchone()
        if not price or float(entry)<=0: pending+=1; continue
        if c.execute('select 1 from shadow_portfolio_marks_v2 where decision_id=? and price_ts=?',(did,price[1])).fetchone(): continue
        ret=(float(price[0])/float(entry)-1.0)*100.0
        c.execute('insert into shadow_portfolio_marks_v2(decision_id,marked_at,price,price_ts,return_pct) values(?,?,?,?,?)',(did,now(),float(price[0]),price[1],ret)); marked+=1
    c.commit(); c.close(); return {'marked':marked,'pending_market_data':pending,'real_trading':False}


def shadow_portfolio_v2_status():
    c=con(); init_shadow_portfolio(c); boundary=_boundary(c)
    decisions=c.execute('select count(*),min(created_at),sum(approved_budget) from shadow_portfolio_decisions_v2').fetchone()
    marks=c.execute('select count(*) from shadow_portfolio_marks_v2').fetchone()[0]
    latest=c.execute('''select d.symbol,d.created_at,d.approved_budget,d.target_fraction,d.entry_price,
        m.price,m.price_ts,m.return_pct from shadow_portfolio_decisions_v2 d
        left join shadow_portfolio_marks_v2 m on m.id=(select max(m2.id) from shadow_portfolio_marks_v2 m2 where m2.decision_id=d.id)
        order by d.created_at desc,d.id desc limit 50''').fetchall()
    c.close()
    rows=[{'symbol':r[0],'created_at':r[1],'approved_budget':r[2],'target_fraction':r[3],'entry_price':r[4],
           'latest_price':r[5],'latest_price_ts':r[6],'return_pct':r[7]} for r in latest]
    return {'started':bool(boundary),'started_at':boundary,'decisions':int(decisions[0] or 0),'first_decision_at':decisions[1],
            'approved_budget_total':float(decisions[2] or 0),'marks':int(marks or 0),'positions':rows,
            'performance_claim':'NOT VERIFIED until prospective marks mature with benchmark and explicit costs',
            'execution_enabled':False,'can_trade':False,'real_trading':False}
