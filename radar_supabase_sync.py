import hashlib, json, os, random, secrets, threading, time, urllib.request, urllib.error

from radar_core import con, init_db, now

SYNC_URL = os.environ.get('SUPABASE_SYNC_URL', '').strip()
SYNC_TOKEN = os.environ.get('RADAR_SYNC_TOKEN', '').strip()
NODE_ID = os.environ.get('RADAR_NODE_ID', 'cloud-primary').strip() or 'cloud-primary'
MAX_SYNC_BATCH = 250
RETRYABLE_HTTP = {408, 425, 429, 500, 502, 503, 504}
SYNC_HTTP_TIMEOUT_SECONDS = max(5.0, float(os.environ.get('RADAR_SUPABASE_SYNC_TIMEOUT_SECONDS', '12') or 12))
SYNC_HTTP_ATTEMPTS = max(1, min(5, int(os.environ.get('RADAR_SUPABASE_SYNC_ATTEMPTS', '3') or 3)))
CIRCUIT_FAILURE_THRESHOLD = max(2, int(os.environ.get('RADAR_SUPABASE_CIRCUIT_FAILURES', '3') or 3))
CIRCUIT_COOLDOWN_SECONDS = max(15.0, float(os.environ.get('RADAR_SUPABASE_CIRCUIT_COOLDOWN_SECONDS', '90') or 90))

# SQLite ids are local to one ephemeral runtime. Railway redeploys may recreate the
# database and restart ids from 1, so sending the raw local id with a stable NODE_ID
# collides with prior Supabase (origin_node, origin_id) keys and silently drops new
# rows under ignoreDuplicates=True. A per-process session prefix preserves NODE_ID
# while making append-only origin ids globally unique across deploys/restarts.
_SYNC_SESSION = (
    os.environ.get('RADAR_SYNC_SESSION_ID', '').strip()
    or ':'.join(
        x for x in (
            os.environ.get('RAILWAY_DEPLOYMENT_ID', '').strip(),
            os.environ.get('RAILWAY_REPLICA_ID', '').strip(),
            secrets.token_hex(8),
        ) if x
    )
)
_SYNC_PREFIX = int.from_bytes(hashlib.sha256(_SYNC_SESSION.encode('utf-8')).digest()[:4], 'big') & 0x7FFFFFFF


class SupabaseCircuitOpen(RuntimeError):
    """Transient fail-fast signal while the Supabase sync circuit is cooling down."""


_RESILIENCE_LOCK = threading.RLock()
_RESILIENCE = {
    'requests': 0,
    'successes': 0,
    'terminal_failures': 0,
    'retry_attempts': 0,
    'consecutive_failures': 0,
    'recoveries': 0,
    'circuit_open_count': 0,
    'circuit_open_until_monotonic': 0.0,
    'last_success_epoch': None,
    'last_error_epoch': None,
    'last_error_type': None,
    'last_error': None,
    'last_latency_ms': None,
    'last_attempts_used': 0,
    'last_batch_counts': {},
}


def _origin_id(local_id):
    """Return an exact bigint-safe decimal string for JSON/Deno/PostgREST transport.

    The composite value can exceed JavaScript's 53-bit safe integer range. Sending it
    as a JSON number lets Deno round adjacent ids to the same value. PostgreSQL bigint
    accepts the decimal string without loss, preserving the exact provenance key.
    """
    local_id = int(local_id)
    if local_id < 0 or local_id >= 2**32:
        raise ValueError('local origin id out of supported range')
    return str((_SYNC_PREFIX << 32) | local_id)


def enabled():
    return bool(SYNC_URL and SYNC_TOKEN)


def _reset_resilience_state_for_tests():
    with _RESILIENCE_LOCK:
        _RESILIENCE.update({
            'requests': 0,
            'successes': 0,
            'terminal_failures': 0,
            'retry_attempts': 0,
            'consecutive_failures': 0,
            'recoveries': 0,
            'circuit_open_count': 0,
            'circuit_open_until_monotonic': 0.0,
            'last_success_epoch': None,
            'last_error_epoch': None,
            'last_error_type': None,
            'last_error': None,
            'last_latency_ms': None,
            'last_attempts_used': 0,
            'last_batch_counts': {},
        })


def _circuit_remaining_seconds():
    with _RESILIENCE_LOCK:
        return max(0.0, float(_RESILIENCE['circuit_open_until_monotonic']) - time.monotonic())


def sync_telemetry():
    """Return secret-free operational telemetry; missing transport is never data=0."""
    with _RESILIENCE_LOCK:
        state = dict(_RESILIENCE)
        state['last_batch_counts'] = dict(_RESILIENCE.get('last_batch_counts') or {})
    remaining = max(0.0, float(state.pop('circuit_open_until_monotonic', 0.0)) - time.monotonic())
    if not enabled():
        status = 'NOT_CONFIGURED'
    elif remaining > 0:
        status = 'CIRCUIT_OPEN'
    elif int(state.get('consecutive_failures') or 0) > 0:
        status = 'DEGRADED'
    elif state.get('last_success_epoch') is None:
        status = 'STARTING'
    else:
        status = 'HEALTHY'
    state.update({
        'status': status,
        'configured': enabled(),
        'node_id': NODE_ID,
        'circuit_open': remaining > 0,
        'circuit_remaining_seconds': round(remaining, 3),
        'failure_threshold': CIRCUIT_FAILURE_THRESHOLD,
        'cooldown_seconds': CIRCUIT_COOLDOWN_SECONDS,
        'default_timeout_seconds': SYNC_HTTP_TIMEOUT_SECONDS,
        'default_attempts': SYNC_HTTP_ATTEMPTS,
        'timeout_means_missing_data': False,
        'empty_response_means_zero_evidence': False,
        'cursors_advance_only_after_remote_success': True,
        'real_trading': False,
    })
    return state


def _before_post():
    remaining = _circuit_remaining_seconds()
    if remaining > 0:
        raise SupabaseCircuitOpen(f'Supabase sync circuit open; retry after {remaining:.1f}s')
    with _RESILIENCE_LOCK:
        _RESILIENCE['requests'] += 1


def _record_success(started, attempts_used):
    latency_ms = round((time.monotonic() - started) * 1000.0, 2)
    with _RESILIENCE_LOCK:
        if int(_RESILIENCE.get('consecutive_failures') or 0) > 0:
            _RESILIENCE['recoveries'] += 1
        _RESILIENCE['successes'] += 1
        _RESILIENCE['consecutive_failures'] = 0
        _RESILIENCE['circuit_open_until_monotonic'] = 0.0
        _RESILIENCE['last_success_epoch'] = time.time()
        _RESILIENCE['last_latency_ms'] = latency_ms
        _RESILIENCE['last_attempts_used'] = int(attempts_used)
        _RESILIENCE['last_error_type'] = None
        _RESILIENCE['last_error'] = None


def _record_failure(exc, started, attempts_used):
    latency_ms = round((time.monotonic() - started) * 1000.0, 2)
    with _RESILIENCE_LOCK:
        _RESILIENCE['terminal_failures'] += 1
        _RESILIENCE['consecutive_failures'] += 1
        _RESILIENCE['last_error_epoch'] = time.time()
        _RESILIENCE['last_error_type'] = type(exc).__name__
        _RESILIENCE['last_error'] = str(exc)[:500]
        _RESILIENCE['last_latency_ms'] = latency_ms
        _RESILIENCE['last_attempts_used'] = int(attempts_used)
        if int(_RESILIENCE['consecutive_failures']) >= CIRCUIT_FAILURE_THRESHOLD:
            was_open = float(_RESILIENCE.get('circuit_open_until_monotonic') or 0.0) > time.monotonic()
            _RESILIENCE['circuit_open_until_monotonic'] = time.monotonic() + CIRCUIT_COOLDOWN_SECONDS
            if not was_open:
                _RESILIENCE['circuit_open_count'] += 1


def _record_retry():
    with _RESILIENCE_LOCK:
        _RESILIENCE['retry_attempts'] += 1


def _set_batch_counts(payload):
    names = (
        'market_snapshots', 'information_events', 'system_runs', 'source_reputation',
        'silence_alerts', 'notifications', 'nodes', 'paper_agents', 'paper_positions',
        'paper_trades', 'portfolio_values',
    )
    counts = {name: len(payload.get(name) or []) for name in names}
    with _RESILIENCE_LOCK:
        _RESILIENCE['last_batch_counts'] = counts


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


def _post(payload, timeout=None, attempts=None, base_delay=0.75):
    """Post one idempotent sync payload with bounded retry, jitter and circuit breaking.

    A failed/timeout request raises. Callers must not translate it into an empty or zero
    dataset. `sync_once` advances SQLite cursors only after this function succeeds.
    """
    timeout = SYNC_HTTP_TIMEOUT_SECONDS if timeout is None else max(1.0, float(timeout))
    attempts = SYNC_HTTP_ATTEMPTS if attempts is None else max(1, min(5, int(attempts)))
    _before_post()
    _set_batch_counts(payload)
    started = time.monotonic()
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        SYNC_URL,
        data=data,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Radar-Token': SYNC_TOKEN,
            'User-Agent': 'InvestmentIntelligenceRadarCloud/1.5.28',
        },
    )
    last_exc = None
    attempts_used = 0
    try:
        for attempt in range(attempts):
            attempts_used = attempt + 1
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    result = json.loads(r.read().decode('utf-8'))
                _record_success(started, attempts_used)
                return result
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode('utf-8', 'replace')
                except Exception:
                    body = ''
                err = RuntimeError(f'Supabase sync HTTP {e.code}: {body[:1200]}')
                if e.code not in RETRYABLE_HTTP or attempt >= attempts - 1:
                    raise err from e
                last_exc = err
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_exc = e
                if attempt >= attempts - 1:
                    raise
            _record_retry()
            jitter = random.uniform(0.80, 1.20)
            time.sleep(max(0.0, float(base_delay)) * (2 ** attempt) * jitter)
        if last_exc is not None:
            raise last_exc
        raise RuntimeError('Supabase sync failed without an explicit error')
    except SupabaseCircuitOpen:
        raise
    except Exception as exc:
        _record_failure(exc, started, attempts_used)
        raise


def sync_once(batch=500):
    if not enabled():
        return {'enabled': False, 'telemetry': sync_telemetry()}

    init_db()
    batch = max(1, min(int(batch), MAX_SYNC_BATCH))
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
            {'id': r[0], 'origin_id': _origin_id(r[0]), 'ts': r[1], 'symbol': r[2], 'price': r[3], 'volume': r[4], 'source': r[5]}
            for r in market_rows
        ],
        'information_events': [
            {'id': r[0], 'origin_id': _origin_id(r[0]), 'ts': r[1], 'source': r[2], 'title': r[3], 'url': r[4], 'category': r[5]}
            for r in event_rows
        ],
        'system_runs': [
            {'id': r[0], 'origin_id': _origin_id(r[0]), 'ts': r[1], 'node_id': NODE_ID, 'kind': r[2], 'status': r[3], 'message': r[4]}
            for r in run_rows
        ],
        'source_reputation': [
            {'source': r[0], 'events': r[1], 'actionable': r[2], 'avg_abs_move': r[3], 'precision_proxy': r[4], 'confidence': r[5], 'score': r[6], 'updated_at': r[7]}
            for r in reputation_rows
        ],
        'silence_alerts': [
            {'id': r[0], 'origin_id': _origin_id(r[0]), 'ts': r[1], 'symbol': r[2], 'return_pct': r[3], 'z_score': r[4], 'recent_public_catalyst': bool(r[5]), 'status': r[6], 'detail': r[7]}
            for r in alert_rows
        ],
        'notifications': [
            {'id': r[0], 'origin_id': _origin_id(r[0]), 'ts': r[1], 'kind': r[2], 'severity': r[3], 'title': r[4], 'body': r[5], 'symbol': r[6], 'read': bool(r[7]), 'dedupe_key': r[8]}
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
            {'id': r[0], 'origin_id': _origin_id(r[0]), 'ts': r[1], 'agent_id': r[2], 'symbol': r[3], 'side': r[4], 'qty': r[5], 'price': r[6], 'gross_value': r[7], 'fees': r[8], 'spread_cost': r[9], 'fx_cost': r[10], 'reason': r[11]}
            for r in trade_rows
        ],
        'portfolio_values': [
            {'id': r[0], 'origin_id': _origin_id(r[0]), 'ts': r[1], 'agent_id': r[2], 'total': r[3], 'cash': r[4], 'invested': r[5], 'drawdown_pct': r[6]}
            for r in mark_rows
        ],
        'node': {
            'node_id': NODE_ID,
            'node_type': 'cloud',
            'name': 'Railway Cloud',
            'enabled': True,
            'app_version': '1.5.28',
            'last_seen': now(),
            'capabilities': {'collector': True, 'paper': True, 'api': True, 'supabase_sync': True},
        },
    }

    result = _post(payload)
    # Cursor advancement is deliberately after remote success. A timeout, HTTP error or
    # open circuit preserves the exact local retry window and cannot turn missing
    # transport into apparent zero evidence.
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
        'origin_session_prefix': _SYNC_PREFIX,
        'remote': result,
        'telemetry': sync_telemetry(),
    }
