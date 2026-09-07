import json, os, time, traceback, threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from radar_core import (
    init_db, collect_market, collect_sec, collect_science, collect_history,
    history_ready, write_status, PID, LOG, STATUS, stats, now,
    profitability_leaders, opportunity_rankings, paper_status, paper_step, con
)
from radar_intelligence import (
    init_intelligence_db, detect_silence, evaluate_source_reputation,
    list_notifications, mark_notifications_read, source_reputation,
    silence_alerts, sync_node_heartbeat, sync_nodes, intelligence_summary
)
from radar_feeds import collect_news, collect_arxiv
from radar_agents import ensure_agents, agents_status, step_all_agents, reset_agents

CONTROL_TOKEN = os.environ.get('RADAR_CONTROL_TOKEN', '').strip()
_state_lock = threading.Lock()

def _control_get(key, default=None):
    try:
        init_db()
        c = con()
        row = c.execute("select value from control where key=?", (key,)).fetchone()
        c.close()
        return row[0] if row else default
    except Exception:
        return default

def _control_set(key, value):
    try:
        init_db()
        c = con()
        c.execute(
            """insert into control(key,value) values(?,?)
               on conflict(key) do update set value=excluded.value""",
            (key, str(value)),
        )
        c.commit()
        c.close()
    except Exception:
        pass

_cloud_enabled = str(_control_get("cloud_enabled", "1")).lower() not in ("0", "false", "no", "off")

def cloud_enabled():
    with _state_lock:
        return _cloud_enabled

def set_cloud_enabled(value):
    global _cloud_enabled
    with _state_lock:
        _cloud_enabled = bool(value)
    _control_set("cloud_enabled", "1" if _cloud_enabled else "0")
    write_status(cloud_enabled=_cloud_enabled, state='ACTIVO' if _cloud_enabled else 'PAUSADO CLOUD')
    return _cloud_enabled

def _read_status():
    try:
        with open(STATUS, 'r', encoding='utf-8') as f:
            d = json.load(f)
    except Exception as e:
        d = {'state': 'STARTING', 'heartbeat': None, 'detail': str(e)}
    d['cloud_enabled'] = cloud_enabled()
    return d

def snapshot_payload():
    prices, events, runs, latest, news = stats()
    return {
        'counts': {'prices': prices, 'events': events, 'runs': runs},
        'latest_prices': [
            {'symbol': r[0], 'price': r[1], 'source': r[2], 'ts': r[3]}
            for r in latest
        ],
        'latest_events': [
            {'source': r[0], 'title': r[1], 'ts': r[2]}
            for r in news
        ],
        'status': _read_status(),
        'leaders': {
            'week': profitability_leaders(7),
            'month': profitability_leaders(30),
            'year': profitability_leaders(365),
        },
        'opportunities': opportunity_rankings(),
        'paper': paper_status(),
        'paper_agents': agents_status(),
        'intelligence': intelligence_summary(),
    }

def worker_loop():
    init_db()
    init_intelligence_db()
    ensure_agents()
    open(PID, 'w').write(str(os.getpid()))
    write_status(
        version='1.3.1',
        state='INICIANDO',
        started_at=now(),
        last_error='',
        cloud_enabled=cloud_enabled(),
    )
    next_market = next_sec = next_science = next_news = next_arxiv = next_silence = next_reputation = 0
    history_attempted = False
    try:
        while True:
            if not cloud_enabled():
                write_status(state='PAUSADO CLOUD', cloud_enabled=False, current_job='')
                time.sleep(2)
                continue

            t = time.time()
            write_status(state='ACTIVO', cloud_enabled=True)
            try:
                if not history_attempted and not history_ready():
                    history_attempted = True
                    write_status(state='CARGANDO HISTÓRICO', current_job='history')
                    n = collect_history()
                    print(f'[collector] history added={n}', flush=True)

                if t >= next_market:
                    write_status(state='RECOPILANDO MERCADO', current_job='market')
                    n = collect_market()
                    print(f'[collector] market added={n}', flush=True)
                    next_market = t + 300
                    paper_step()
                    agents = step_all_agents()
                    print(f'[paper] agents stepped={len(agents)}', flush=True)

                if t >= next_sec:
                    write_status(state='RECOPILANDO SEC', current_job='sec')
                    n = collect_sec()
                    print(f'[collector] sec added={n}', flush=True)
                    next_sec = t + 900

                if t >= next_science:
                    write_status(state='RECOPILANDO CIENCIA', current_job='science')
                    n = collect_science()
                    print(f'[collector] science added={n}', flush=True)
                    next_science = t + 1800

                if t >= next_news:
                    write_status(state='RECOPILANDO NOTICIAS', current_job='news')
                    n = collect_news()
                    print(f'[collector] news added={n}', flush=True)
                    next_news = t + 900

                if t >= next_arxiv:
                    write_status(state='RECOPILANDO ARXIV', current_job='arxiv')
                    n = collect_arxiv()
                    print(f'[collector] arxiv added={n}', flush=True)
                    next_arxiv = t + 3600

                if t >= next_silence:
                    write_status(state='ANALIZANDO SILENCIO', current_job='silence')
                    alerts = detect_silence()
                    print(f'[intelligence] silence alerts={len(alerts)}', flush=True)
                    next_silence = t + 300

                if t >= next_reputation:
                    write_status(state='EVALUANDO FUENTES', current_job='source_reputation')
                    reps = evaluate_source_reputation()
                    print(f'[intelligence] sources scored={len(reps)}', flush=True)
                    next_reputation = t + 21600

                p, e, r, _, _ = stats()
                print(f'[collector] totals prices={p} events={e} runs={r}', flush=True)

            except Exception as e:
                with open(LOG, 'a', encoding='utf-8') as f:
                    f.write(traceback.format_exc() + '\n')
                print('[collector] ERROR ' + repr(e), flush=True)
                write_status(state='ERROR', last_error=str(e))

            write_status(
                state='ESPERANDO SIGUIENTE CICLO',
                current_job='',
                cloud_enabled=True
            )
            time.sleep(10)
    finally:
        try:
            os.remove(PID)
        except OSError:
            pass

def _authorized(h):
    return bool(CONTROL_TOKEN) and h.headers.get('Authorization', '') == 'Bearer ' + CONTROL_TOKEN

def _read_json(h):
    try:
        n = int(h.headers.get('Content-Length', '0') or 0)
        if n <= 0:
            return {}
        return json.loads(h.rfile.read(n).decode('utf-8'))
    except Exception:
        return {}

class _Handler(SimpleHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?', 1)[0]

        if path == '/mobile':
            self.send_response(302)
            self.send_header('Location', '/mobile/')
            self.end_headers()
            return

        if path.startswith('/mobile/') and path != '/mobile/dashboard':
            return super().do_GET()

        if path == '/health':
            self._send(200, {
                'ok': True,
                'service': 'Investment Intelligence Radar Cloud',
                'version': '1.3.1',
                'cloud_enabled': cloud_enabled(),
                'status': _read_status(),
            })
            return

        if path == '/status':
            self._send(200, _read_status())
            return

        if path == '/snapshot':
            self._send(200, snapshot_payload())
            return

        if path == '/mobile/dashboard':
            self._send(200, snapshot_payload())
            return

        if path == '/notifications':
            self._send(200, {'notifications': list_notifications(100, False)})
            return

        if path == '/source-reputation':
            self._send(200, {'sources': source_reputation(100)})
            return

        if path == '/silence-alerts':
            self._send(200, {'alerts': silence_alerts(100, True)})
            return

        if path == '/nodes':
            self._send(200, {'nodes': sync_nodes(100)})
            return

        if path == '/paper-agents':
            self._send(200, {'agents': agents_status()})
            return

        self._send(404, {'ok': False, 'error': 'not found'})

    def do_POST(self):
        path = self.path.split('?', 1)[0]

        if not _authorized(self):
            self._send(401, {'ok': False, 'error': 'unauthorized'})
            return

        if path == '/toggle':
            self._send(200, {
                'ok': True,
                'cloud_enabled': set_cloud_enabled(not cloud_enabled()),
                'status': _read_status(),
            })
            return

        if path == '/collect-now':
            if not history_ready():
                collect_history()
            results = {
                'market': collect_market(),
                'sec': collect_sec(),
                'science': collect_science(),
                'news': collect_news(),
                'arxiv': collect_arxiv(),
                'silence': len(detect_silence()),
                'source_reputation': len(evaluate_source_reputation()),
            }
            paper_step(force=True)
            agents = step_all_agents(force=True)
            results['paper_agents'] = len(agents)
            self._send(200, {
                'ok': True,
                'results': results,
                'snapshot': snapshot_payload(),
            })
            return

        if path == '/intelligence-now':
            results = {
                'silence': len(detect_silence()),
                'source_reputation': len(evaluate_source_reputation()),
            }
            self._send(200, {'ok': True, 'results': results, 'intelligence': intelligence_summary()})
            return

        if path == '/node-heartbeat':
            data = _read_json(self)
            try:
                result = sync_node_heartbeat(
                    data.get('node_id'),
                    node_type=data.get('node_type', 'desktop'),
                    name=data.get('name'),
                    capabilities=data.get('capabilities'),
                    app_version=data.get('app_version'),
                    detail=data.get('detail'),
                )
                self._send(200, {'ok': True, 'node': result})
            except Exception as e:
                self._send(400, {'ok': False, 'error': str(e)})
            return

        if path == '/notifications/read':
            data = _read_json(self)
            n = mark_notifications_read(data.get('ids'))
            self._send(200, {'ok': True, 'updated': n})
            return

        if path == '/paper-agents/step':
            agents = step_all_agents(force=True)
            self._send(200, {'ok': True, 'agents': agents})
            return

        if path == '/paper-agents/reset':
            data = _read_json(self)
            amount = float(data.get('initial_cash', 200.0))
            agents = reset_agents(amount)
            self._send(200, {'ok': True, 'agents': agents})
            return

        self._send(404, {'ok': False, 'error': 'not found'})

    def log_message(self, fmt, *args):
        print('[http]', fmt % args, flush=True)

def main():
    port = os.environ.get('PORT')
    if port:
        threading.Thread(target=worker_loop, name='radar-worker', daemon=True).start()
        p = int(port)
        print(f'Radar cloud HTTP listening on 0.0.0.0:{p}', flush=True)
        ThreadingHTTPServer(('0.0.0.0', p), _Handler).serve_forever()
    else:
        worker_loop()

if __name__ == '__main__':
    main()
