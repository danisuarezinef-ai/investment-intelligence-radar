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


def _post(payload, timeout=25):
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
    c = con()
    market_after = int(_control_get('supabase_market_id', '0') or 0)
    events_after = int(_control_get('supabase_event_id', '0') or 0)
    runs_after = int(_control_get('supabase_run_id', '0') or 0)

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
    return {
        'enabled': True,
        'market': len(market_rows),
        'events': len(event_rows),
        'runs': len(run_rows),
        'remote': result,
    }
