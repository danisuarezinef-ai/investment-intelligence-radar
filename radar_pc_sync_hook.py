import json
import os
import threading
import time
import urllib.error
import urllib.request

PC_SYNC_VERSION = '1.4.0'
CLOUD_BASE = 'https://radar-cloud-production.up.railway.app'


def _data_dir():
    return os.path.join(
        os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
        'InvestmentIntelligenceRadarData',
    )


def _read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            value = json.load(f)
        return value if isinstance(value, dict) else (default or {})
    except Exception:
        return default or {}


def _write_json_atomic(path, value):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def _post(token, payload, timeout=35):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        CLOUD_BASE + '/pc-sync',
        data=data,
        method='POST',
        headers={
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json',
            'User-Agent': 'InvestmentIntelligenceRadarDesktopSync/' + PC_SYNC_VERSION,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _sync_once():
    # Import lazily: in the packaged application this module is available after
    # PyInstaller has initialized the embedded import system.
    from radar_core import con, init_db

    data_dir = _data_dir()
    settings_path = os.path.join(data_dir, 'desktop_settings.json')
    state_path = os.path.join(data_dir, 'pc_sync_state.json')
    settings = _read_json(settings_path)
    token = str(settings.get('cloud_control_token') or '').strip()
    node_id = str(settings.get('node_id') or '').strip()
    if not token or not node_id:
        return {'enabled': False, 'reason': 'waiting_for_cloud_control'}

    state = _read_json(state_path, {
        'market_id': 0,
        'event_id': 0,
        'run_id': 0,
    })
    market_after = int(state.get('market_id') or 0)
    event_after = int(state.get('event_id') or 0)
    run_after = int(state.get('run_id') or 0)

    init_db()
    c = con()
    try:
        market = c.execute(
            '''select id,ts,symbol,price,volume,source from market_snapshots
               where id>? order by id limit 300''',
            (market_after,),
        ).fetchall()
        events = c.execute(
            '''select id,ts,source,title,url,category from information_events
               where id>? order by id limit 300''',
            (event_after,),
        ).fetchall()
        runs = c.execute(
            '''select id,ts,job,status,detail from system_runs
               where id>? order by id limit 300''',
            (run_after,),
        ).fetchall()
    finally:
        c.close()

    payload = {
        'node_id': node_id,
        'name': os.environ.get('COMPUTERNAME', 'Windows PC'),
        'app_version': PC_SYNC_VERSION,
        'capabilities': ['local-collector', 'paper-simulator', 'desktop-ui', 'persistent-sync'],
        'market_snapshots': [
            {
                'id': r[0], 'origin_id': r[0], 'origin_node': node_id,
                'ts': r[1], 'symbol': r[2], 'price': r[3], 'volume': r[4],
                'source': r[5],
            }
            for r in market
        ],
        'information_events': [
            {
                'id': r[0], 'origin_id': r[0], 'origin_node': node_id,
                'ts': r[1], 'source': r[2], 'title': r[3], 'url': r[4],
                'category': r[5],
            }
            for r in events
        ],
        'system_runs': [
            {
                'id': r[0], 'origin_id': r[0], 'origin_node': node_id,
                'ts': r[1], 'node_id': node_id, 'kind': r[2], 'status': r[3],
                'message': r[4],
            }
            for r in runs
        ],
    }

    result = _post(token, payload)
    if not result.get('ok'):
        raise RuntimeError(str(result.get('error') or 'PC sync rejected'))

    if market:
        state['market_id'] = market[-1][0]
    if events:
        state['event_id'] = events[-1][0]
    if runs:
        state['run_id'] = runs[-1][0]
    state['last_success'] = time.time()
    state['last_error'] = ''
    state['last_counts'] = {
        'market': len(market), 'events': len(events), 'runs': len(runs),
    }
    _write_json_atomic(state_path, state)
    return {'enabled': True, **state['last_counts']}


def _loop():
    # Give the desktop process enough time to initialize its DB/settings first.
    time.sleep(8)
    while True:
        try:
            _sync_once()
        except urllib.error.HTTPError as exc:
            state_path = os.path.join(_data_dir(), 'pc_sync_state.json')
            state = _read_json(state_path)
            state['last_error'] = 'HTTP ' + str(exc.code)
            _write_json_atomic(state_path, state)
        except Exception as exc:
            state_path = os.path.join(_data_dir(), 'pc_sync_state.json')
            state = _read_json(state_path)
            state['last_error'] = str(exc)[:500]
            _write_json_atomic(state_path, state)
        time.sleep(60)


# Runtime-hook entrypoint. It never blocks application startup.
if os.name == 'nt':
    threading.Thread(target=_loop, name='radar-pc-persistent-sync', daemon=True).start()
