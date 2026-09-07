import json, os, urllib.request, urllib.error

from radar_core import con, init_db, now

SYNC_URL = os.environ.get('SUPABASE_SYNC_URL', '').strip()
SYNC_TOKEN = os.environ.get('RADAR_SYNC_TOKEN', '').strip()
NODE_ID = os.environ.get('RADAR_NODE_ID', 'cloud-primary').strip() or 'cloud-primary'


def enabled():
    return bool(SYNC_URL and SYNC_TOKEN)


def _control_get(key, default='0'):
    try:
        c = con()
        row = c.execute('select value from control where key=?', (key,)).fetchone()
        c.close()
        return row[0] if row else default
    except Exception:
        return default


def _control_set(key, value):
    c = con()
    c.execute(
        '''insert into control(key,value) values(?,?)
           on conflict(key) do update set value=excluded.value''',
        (key, str(value)),
    )
    c.commit()
    c.close()


def _table_exists(c, name):
    try:
        return c.execute(
            "select 1 from sqlite_master where type='table' and name=?", (name,)
        ).fetchone() is not None
    except Exception:
        return False


def _post(payload, timeout=30):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        SYNC_URL,
        data=data,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Radar-Token': SYNC_TOKEN,
            'User-Agent': 'InvestmentIntelligenceRadarCloud/1.4',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8', 'replace')
        except Exception:
            body = ''
        raise RuntimeError(f'Supabase sync HTTP {e.code}: {body[:1200]}') from e


def sync_once(batch=500):
    if not enabled():
        return {'enabled': False}

    init_db()
    market_after = int(_control_get('supabase_market_id', '0') or 0)
    events_after = int(_control_get('supabase_event_id', '0') or 0)
    runs_after = int(_control_get('supabase_run_id', '0') or 0)
    trades_after = int(_control_get('supabase_agent_trade_id', '0') or 0)
    marks_after = int(_control_get('supabase_agent_mark_id', '0') or 0)
    alerts_after = int(_control_get('supabase_alert_id', '0') or 0)
    notifications_after = int(_control_get('supabase_notification_id', '0') or 0)

    c = con()
    market_rows = c.execute(
        'select id,ts,symbol,price,volume,source from market_snapshots where id>? order by id limit ?',
        (market_after, batch),
    ).fetchall()
    event_rows = c.execute(
        'select id,ts,source,title,url,category from information_events where id>? order by id limit ?',
        (events_after, batch),
    ).fetchall()
    run_rows = c.execute(
        'select id,ts,job,status,detail from system_runs where id>? order by id limit ?',
        (runs_after, batch),
    ).fetchall()

    agent_rows = []
    position_rows = []
    trade_rows = []
    mark_rows = []
    reputation_rows = []
    alert_rows = []
    notification_rows = []
    node_rows = []

    if _table_exists(c, 'paper_agents'):
        agent_rows = c.execute(
            'select agent_id,name,strategy,initial_cash,cash,enabled,last_rebalance,created_at from paper_agents order by agent_id'
        ).fetchall()
    if _table_exists(c, 'paper_agent_positions'):
        position_rows = c.execute(
            'select agent_id,symbol,qty,avg_price,updated_at from paper_agent_positions order by agent_id,symbol'
        ).fetchall()
    if _table_exists(c, 'paper_agent_trades'):
        trade_rows = c.execute(
            '''select id,ts,agent_id,symbol,side,qty,price,gross_value,fees,spread_cost,fx_cost,reason
               from paper_agent_trades where id>? order by id limit ?''',
            (trades_after, batch),
        ).fetchall()
    if _table_exists(c, 'paper_agent_marks'):
        mark_rows = c.execute(
            '''select id,ts,agent_id,total,cash,invested,drawdown_pct
               from paper_agent_marks where id>? order by id limit ?''',
            (marks_after, batch),
        ).fetchall()
    if _table_exists(c, 'source_reputation'):
        reputation_rows = c.execute(
            '''select source,events,actionable,avg_abs_move,precision_proxy,confidence,score,updated_at
               from source_reputation order by score desc'''
        ).fetchall()
    if _table_exists(c, 'silence_alerts'):
        alert_rows = c.execute(
            '''select id,ts,symbol,return_pct,z_score,recent_public_catalyst,status,detail
               from silence_alerts where id>? order by id limit ?''',
            (alerts_after, batch),
        ).fetchall()
    if _table_exists(c, 'notifications'):
        notification_rows = c.execute(
            '''select id,ts,kind,severity,title,body,symbol,read,dedupe_key
               from notifications where id>? order by id limit ?''',
            (notifications_after, batch),
        ).fetchall()
    if _table_exists(c, 'sync_nodes'):
        node_rows = c.execute(
            '''select node_id,node_type,name,capabilities,last_seen,app_version,detail
               from sync_nodes order by last_seen desc limit 200'''
        ).fetchall()
    c.close()

    payload = {
        'node_id': NODE_ID,
        'market_snapshots': [
            {'id': r[0], 'origin_id': r[0], 'ts': r[1], 'symbol': r[2], 'price': r[3], 'volume': r[4], 'source': r[5]}
            for r in market_rows
        ],
        'information_events': [
            {'id': r[0], 'origin_id': r[0], 'ts': r[1], 'source': r[2], 'title': r[3], 'url': r[4], 'category': r[5]}
            for r in event_rows
        ],
        'system_runs': [
            {'id': r[0], 'origin_id': r[0], 'ts': r[1], 'node_id': NODE_ID, 'kind': r[2], 'status': r[3], 'message': r[4]}
            for r in run_rows
        ],
        'source_reputation': [
            {'source': r[0], 'events': r[1], 'actionable': r[2], 'avg_abs_move': r[3], 'precision_proxy': r[4], 'confidence': r[5], 'score': r[6], 'updated_at': r[7]}
            for r in reputation_rows
        ],
        'silence_alerts': [
            {'id': r[0], 'origin_id': r[0], 'ts': r[1], 'symbol': r[2], 'return_pct': r[3], 'z_score': r[4], 'recent_public_catalyst': bool(r[5]), 'status': r[6], 'detail': r[7]}
            for r in alert_rows
        ],
        'notifications': [
            {'id': r[0], 'origin_id': r[0], 'ts': r[1], 'kind': r[2], 'severity': r[3], 'title': r[4], 'body': r[5], 'symbol': r[6], 'read': bool(r[7]), 'dedupe_key': r[8]}
            for r in notification_rows
        ],
        'nodes': [
            {'node_id': r[0], 'node_type': r[1], 'name': r[2], 'capabilities': r[3], 'last_seen': r[4], 'app_version': r[5], 'detail': r[6]}
            for r in node_rows
        ],
        'paper_agents': [
            {'agent_id': r[0], 'name': r[1], 'strategy': r[2], 'initial_cash': r[3], 'cash': r[4], 'enabled': bool(r[5]), 'last_rebalance': r[6], 'created_at': r[7]}
            for r in agent_rows
        ],
        'paper_positions': [
            {'agent_id': r[0], 'symbol': r[1], 'qty': r[2], 'avg_price': r[3], 'updated_at': r[4]}
            for r in position_rows
        ],
        'paper_trades': [
            {'id': r[0], 'origin_id': r[0], 'ts': r[1], 'agent_id': r[2], 'symbol': r[3], 'side': r[4], 'qty': r[5], 'price': r[6], 'gross_value': r[7], 'fees': r[8], 'spread_cost': r[9], 'fx_cost': r[10], 'reason': r[11]}
            for r in trade_rows
        ],
        'portfolio_values': [
            {'id': r[0], 'origin_id': r[0], 'ts': r[1], 'agent_id': r[2], 'total': r[3], 'cash': r[4], 'invested': r[5], 'drawdown_pct': r[6]}
            for r in mark_rows
        ],
        'node': {
            'node_id': NODE_ID,
            'node_type': 'cloud',
            'name': 'Railway Cloud',
            'enabled': True,
            'app_version': '1.4',
            'last_seen': now(),
            'capabilities': {'collector': True, 'paper': True, 'api': True, 'supabase_sync': True},
        },
    }

    result = _post(payload)
    if market_rows:
        _control_set('supabase_market_id', market_rows[-1][0])
    if event_rows:
        _control_set('supabase_event_id', event_rows[-1][0])
    if run_rows:
        _control_set('supabase_run_id', run_rows[-1][0])
    if trade_rows:
        _control_set('supabase_agent_trade_id', trade_rows[-1][0])
    if mark_rows:
        _control_set('supabase_agent_mark_id', mark_rows[-1][0])
    if alert_rows:
        _control_set('supabase_alert_id', alert_rows[-1][0])
    if notification_rows:
        _control_set('supabase_notification_id', notification_rows[-1][0])

    return {
        'enabled': True,
        'market': len(market_rows),
        'events': len(event_rows),
        'runs': len(run_rows),
        'reputation': len(reputation_rows),
        'alerts': len(alert_rows),
        'notifications': len(notification_rows),
        'nodes': len(node_rows),
        'agents': len(agent_rows),
        'positions': len(position_rows),
        'trades': len(trade_rows),
        'marks': len(mark_rows),
        'remote': result,
    }
