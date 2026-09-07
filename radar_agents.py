import math, statistics
from datetime import datetime, timezone

from radar_core import con, init_db, now, history_ready, collect_history, opportunity_rankings, _latest_prices

AGENTS = {
    'conservative': {
        'name': 'Conservador', 'initial_cash': 200.0,
        'target_invested': 0.55, 'per_position': 0.16, 'max_positions': 4,
        'tiers': ('bajo',), 'min_score': 0.0, 'stop_loss': -5.0,
        'fee_pct': 0.0008, 'spread_pct': 0.0008, 'fx_pct': 0.0005,
    },
    'balanced': {
        'name': 'Equilibrado', 'initial_cash': 200.0,
        'target_invested': 0.70, 'per_position': 0.20, 'max_positions': 5,
        'tiers': ('bajo', 'intermedio'), 'min_score': 0.0, 'stop_loss': -7.0,
        'fee_pct': 0.0010, 'spread_pct': 0.0010, 'fx_pct': 0.0007,
    },
    'aggressive': {
        'name': 'Agresivo', 'initial_cash': 200.0,
        'target_invested': 0.82, 'per_position': 0.24, 'max_positions': 5,
        'tiers': ('intermedio', 'alto', 'bajo'), 'min_score': -1.5, 'stop_loss': -10.0,
        'fee_pct': 0.0011, 'spread_pct': 0.0012, 'fx_pct': 0.0008,
    },
    'high_conviction': {
        'name': 'Alta convicción', 'initial_cash': 200.0,
        'target_invested': 0.90, 'per_position': 0.34, 'max_positions': 3,
        'tiers': ('bajo', 'intermedio', 'alto'), 'min_score': 1.0, 'stop_loss': -12.0,
        'fee_pct': 0.0010, 'spread_pct': 0.0010, 'fx_pct': 0.0007,
    },
    'experimental': {
        'name': 'Experimental', 'initial_cash': 200.0,
        'target_invested': 0.92, 'per_position': 0.36, 'max_positions': 4,
        'tiers': ('alto', 'intermedio', 'bajo'), 'min_score': -4.0, 'stop_loss': -15.0,
        'fee_pct': 0.0013, 'spread_pct': 0.0016, 'fx_pct': 0.0010,
    },
}

def init_agents_db():
    init_db()
    c = con()
    c.execute("""create table if not exists paper_agents(
        agent_id text primary key,
        name text not null,
        strategy text not null,
        initial_cash real not null,
        cash real not null,
        enabled integer not null default 1,
        last_rebalance text,
        created_at text not null
    )""")
    c.execute("""create table if not exists paper_agent_positions(
        agent_id text not null,
        symbol text not null,
        qty real not null,
        avg_price real not null,
        updated_at text not null,
        primary key(agent_id,symbol)
    )""")
    c.execute("""create table if not exists paper_agent_trades(
        id integer primary key,
        ts text not null,
        agent_id text not null,
        symbol text not null,
        side text not null,
        qty real not null,
        price real not null,
        gross_value real not null,
        fees real not null default 0,
        spread_cost real not null default 0,
        fx_cost real not null default 0,
        reason text
    )""")
    c.execute("""create table if not exists paper_agent_marks(
        id integer primary key,
        ts text not null,
        agent_id text not null,
        total real not null,
        cash real not null,
        invested real not null,
        drawdown_pct real not null default 0
    )""")
    c.execute("create index if not exists idx_agent_marks on paper_agent_marks(agent_id,ts)")
    c.execute("create index if not exists idx_agent_trades on paper_agent_trades(agent_id,ts)")
    c.commit()
    c.close()

def ensure_agents(reset=False, initial_cash=200.0):
    init_agents_db()
    c = con()
    if reset:
        c.execute('delete from paper_agent_positions')
        c.execute('delete from paper_agent_trades')
        c.execute('delete from paper_agent_marks')
        c.execute('delete from paper_agents')
    for agent_id, cfg in AGENTS.items():
        amount = max(50.0, float(initial_cash if initial_cash is not None else cfg['initial_cash']))
        row = c.execute('select 1 from paper_agents where agent_id=?', (agent_id,)).fetchone()
        if not row:
            c.execute(
                """insert into paper_agents(agent_id,name,strategy,initial_cash,cash,enabled,last_rebalance,created_at)
                   values(?,?,?,?,?,1,null,?)""",
                (agent_id, cfg['name'], agent_id, amount, amount, now()),
            )
    c.commit()
    c.close()
    return agents_status()

def _positions(agent_id, prices):
    c = con()
    rows = c.execute(
        'select symbol,qty,avg_price from paper_agent_positions where agent_id=? order by symbol',
        (agent_id,),
    ).fetchall()
    c.close()
    out = []
    invested = 0.0
    for symbol, qty, avg_price in rows:
        price = float(prices.get(symbol, avg_price))
        value = float(qty) * price
        invested += value
        out.append({
            'symbol': symbol,
            'qty': float(qty),
            'avg_price': float(avg_price),
            'price': price,
            'value': value,
            'pnl_pct': ((price / float(avg_price)) - 1.0) * 100.0 if avg_price else 0.0,
        })
    return out, invested

def _risk_stats(agent_id):
    c = con()
    rows = c.execute(
        'select ts,total from paper_agent_marks where agent_id=? order by id desc limit 120',
        (agent_id,),
    ).fetchall()
    c.close()
    rows = list(reversed(rows))
    if not rows:
        return {'drawdown_pct': 0.0, 'max_drawdown_pct': 0.0, 'sharpe': 0.0, 'marks': 0}
    vals = [float(r[1]) for r in rows if r[1] is not None and float(r[1]) > 0]
    if not vals:
        return {'drawdown_pct': 0.0, 'max_drawdown_pct': 0.0, 'sharpe': 0.0, 'marks': 0}
    peak = vals[0]
    max_dd = 0.0
    for v in vals:
        peak = max(peak, v)
        dd = (v / peak - 1.0) * 100.0 if peak else 0.0
        max_dd = min(max_dd, dd)
    current_dd = (vals[-1] / max(vals) - 1.0) * 100.0 if max(vals) else 0.0
    rets = []
    for i in range(1, len(vals)):
        if vals[i-1] > 0:
            rets.append(vals[i] / vals[i-1] - 1.0)
    if len(rets) >= 4 and statistics.pstdev(rets) > 1e-12:
        sharpe = statistics.mean(rets) / statistics.pstdev(rets) * math.sqrt(252)
    else:
        sharpe = 0.0
    return {
        'drawdown_pct': current_dd,
        'max_drawdown_pct': max_dd,
        'sharpe': sharpe,
        'marks': len(vals),
    }

def agent_status(agent_id):
    init_agents_db()
    prices = _latest_prices()
    c = con()
    a = c.execute(
        'select name,initial_cash,cash,enabled,last_rebalance from paper_agents where agent_id=?',
        (agent_id,),
    ).fetchone()
    if not a:
        c.close()
        return {'configured': False, 'agent_id': agent_id}
    trades = c.execute(
        """select ts,symbol,side,qty,price,gross_value,fees,spread_cost,fx_cost,reason
           from paper_agent_trades where agent_id=? order by id desc limit 12""",
        (agent_id,),
    ).fetchall()
    c.close()
    positions, invested = _positions(agent_id, prices)
    cash = float(a[2])
    total = cash + invested
    initial = float(a[1])
    risk = _risk_stats(agent_id)
    return {
        'configured': True,
        'agent_id': agent_id,
        'name': a[0],
        'initial': initial,
        'cash': cash,
        'enabled': bool(a[3]),
        'last_rebalance': a[4],
        'invested': invested,
        'total': total,
        'pnl': total - initial,
        'pnl_pct': (total / initial - 1.0) * 100.0 if initial else 0.0,
        'positions': positions,
        'trades': [
            {
                'ts': t[0], 'symbol': t[1], 'side': t[2], 'qty': t[3],
                'price': t[4], 'gross_value': t[5], 'fees': t[6],
                'spread_cost': t[7], 'fx_cost': t[8], 'reason': t[9]
            } for t in trades
        ],
        **risk,
    }

def agents_status():
    init_agents_db()
    return [agent_status(agent_id) for agent_id in AGENTS]

def _candidate_list(cfg, rankings):
    merged = []
    seen = set()
    for tier in cfg['tiers']:
        for r in rankings.get(tier, []):
            if r['symbol'] in seen:
                continue
            seen.add(r['symbol'])
            merged.append(r)
    merged.sort(key=lambda x: x['score'], reverse=True)
    return merged

def _costs(cfg, gross):
    fees = gross * cfg['fee_pct']
    spread = gross * cfg['spread_pct']
    fx = gross * cfg['fx_pct']
    return fees, spread, fx

def _mark_agent(agent_id):
    st = agent_status(agent_id)
    if not st.get('configured'):
        return st
    c = con()
    prior = c.execute(
        'select max(total) from paper_agent_marks where agent_id=?', (agent_id,)
    ).fetchone()[0]
    peak = max(float(prior or 0), st['total'])
    dd = (st['total'] / peak - 1.0) * 100.0 if peak else 0.0
    c.execute(
        'insert into paper_agent_marks(ts,agent_id,total,cash,invested,drawdown_pct) values(?,?,?,?,?,?)',
        (now(), agent_id, st['total'], st['cash'], st['invested'], dd),
    )
    c.commit()
    c.close()
    return agent_status(agent_id)

def step_agent(agent_id, force=False):
    ensure_agents()
    cfg = AGENTS[agent_id]
    st = agent_status(agent_id)
    if not st.get('configured') or not st.get('enabled'):
        return st
    if not history_ready():
        collect_history()
        st = agent_status(agent_id)
    if not force and st.get('last_rebalance'):
        try:
            dt = datetime.fromisoformat(st['last_rebalance'])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - dt).total_seconds() < 1800:
                return _mark_agent(agent_id)
        except Exception:
            pass

    rankings = opportunity_rankings(12)
    candidates = _candidate_list(cfg, rankings)
    prices = _latest_prices()
    scoremap = {r['symbol']: r['score'] for tier in rankings.values() for r in tier}

    c = con()
    for p in st['positions']:
        score = scoremap.get(p['symbol'])
        should_sell = score is None or score < cfg['min_score'] - 3.0 or p['pnl_pct'] < cfg['stop_loss']
        if not should_sell:
            continue
        price = prices.get(p['symbol'])
        if not price:
            continue
        gross = p['qty'] * price
        fees, spread, fx = _costs(cfg, gross)
        net = max(0.0, gross - fees - spread - fx)
        c.execute('update paper_agents set cash=cash+? where agent_id=?', (net, agent_id))
        c.execute('delete from paper_agent_positions where agent_id=? and symbol=?', (agent_id, p['symbol']))
        c.execute(
            """insert into paper_agent_trades(ts,agent_id,symbol,side,qty,price,gross_value,fees,spread_cost,fx_cost,reason)
               values(?,?,?,?,?,?,?,?,?,?,?)""",
            (now(), agent_id, p['symbol'], 'SELL', p['qty'], price, gross,
             fees, spread, fx, 'Salida por deterioro, riesgo o stop-loss'),
        )
    c.commit()
    c.close()

    st = agent_status(agent_id)
    total = st['total']
    target_invested = total * cfg['target_invested']
    per_cap = total * cfg['per_position']
    need = max(0.0, target_invested - st['invested'])
    cash = st['cash']
    held = {p['symbol'] for p in st['positions']}
    slots = max(0, cfg['max_positions'] - len(held))

    c = con()
    for r in candidates:
        if slots <= 0 or need < 10 or cash < 10:
            break
        symbol = r['symbol']
        price = prices.get(symbol)
        if not price or price <= 0 or symbol in held or r['score'] < cfg['min_score']:
            continue
        gross_budget = min(per_cap, need, cash * 0.97)
        if gross_budget < 10:
            continue
        fee_rate = cfg['fee_pct'] + cfg['spread_pct'] + cfg['fx_pct']
        gross = gross_budget / (1.0 + fee_rate)
        fees, spread, fx = _costs(cfg, gross)
        total_cost = gross + fees + spread + fx
        if total_cost > cash or gross < 8:
            continue
        qty = gross / price
        c.execute('update paper_agents set cash=cash-? where agent_id=?', (total_cost, agent_id))
        c.execute(
            """insert or replace into paper_agent_positions(agent_id,symbol,qty,avg_price,updated_at)
               values(?,?,?,?,?)""",
            (agent_id, symbol, qty, price, now()),
        )
        c.execute(
            """insert into paper_agent_trades(ts,agent_id,symbol,side,qty,price,gross_value,fees,spread_cost,fx_cost,reason)
               values(?,?,?,?,?,?,?,?,?,?,?)""",
            (now(), agent_id, symbol, 'BUY', qty, price, gross, fees, spread, fx,
             f"Score {r['score']:.2f} · riesgo {r['risk']} · estrategia {cfg['name']}"),
        )
        cash -= total_cost
        need -= gross
        held.add(symbol)
        slots -= 1
    c.execute('update paper_agents set last_rebalance=? where agent_id=?', (now(), agent_id))
    c.commit()
    c.close()
    return _mark_agent(agent_id)

def step_all_agents(force=False):
    ensure_agents()
    results = []
    for agent_id in AGENTS:
        results.append(step_agent(agent_id, force=force))
    return results

def reset_agents(initial_cash=200.0):
    ensure_agents(reset=True, initial_cash=initial_cash)
    return step_all_agents(force=True)
