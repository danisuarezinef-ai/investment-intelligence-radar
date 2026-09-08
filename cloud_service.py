import json
import os
import sqlite3
import threading
import time
import urllib.parse

import run_worker
from radar_core import con, fetch, init_db, log, now, write_status
from radar_supabase_sync import enabled as supabase_sync_enabled, sync_once, _post as forward_supabase
from radar_learning import (
    init_learning_db, run_learning_cycle, dashboard_v2, capture_predictions,
    evaluate_predictions, learn_if_ready, backtest_point_in_time, lists_369,
    calibration_summary, audit_system
)
from radar_causal import build_causal_graph, graph_summary, symbol_causal_summary


def collect_science_safe():
    """Europe PMC collector with fully encoded query parameters and no control characters."""
    init_db()
    query = 'artificial intelligence OR semiconductor OR battery OR fusion energy OR quantum computing'
    params = urllib.parse.urlencode({'query': query, 'format': 'json', 'pageSize': 15})
    url = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + params
    if any(ord(ch) < 32 for ch in url):
        raise RuntimeError('Europe PMC URL contains control characters')
    added = 0; seen = 0
    try:
        data = json.loads(fetch(url, 25, {'Accept': 'application/json'}))
        results = (data.get('resultList') or {}).get('result') or []
        seen = len(results); c = con()
        try:
            for item in results:
                title = ' '.join(str(item.get('title') or '').split())
                pid = item.get('pmid') or item.get('pmcid') or item.get('id')
                if not title or not pid: continue
                article_url = 'https://europepmc.org/article/MED/' + urllib.parse.quote(str(pid), safe='')
                try:
                    c.execute('insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)',
                              (now(), 'Europe PMC', title, article_url, 'science')); added += 1
                except sqlite3.IntegrityError: pass
            c.commit()
        finally: c.close()
        log('science', 'OK', f'{added} eventos nuevos de {seen} recuperados')
        write_status(science_status='OK', science_seen=seen, last_error='')
    except Exception as exc:
        log('science', 'ERROR', str(exc)); write_status(science_status='ERROR', last_error=str(exc))
    return added


run_worker.collect_science = collect_science_safe
BaseHandler = run_worker._Handler


class MobileHandler(BaseHandler):
    STATIC = {
        '/': ('mobile/index.html', 'text/html; charset=utf-8'),
        '/mobile': ('mobile/index.html', 'text/html; charset=utf-8'),
        '/mobile/': ('mobile/index.html', 'text/html; charset=utf-8'),
        '/mobile/index.html': ('mobile/index.html', 'text/html; charset=utf-8'),
        '/mobile/manifest.webmanifest': ('mobile/manifest.webmanifest', 'application/manifest+json; charset=utf-8'),
        '/mobile/sw.js': ('mobile/sw.js', 'application/javascript; charset=utf-8'),
    }

    def _send_static(self, relpath, content_type):
        path = os.path.join(os.path.dirname(__file__), relpath)
        try:
            with open(path, 'rb') as f: body = f.read()
            self.send_response(200); self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-cache' if relpath.endswith('sw.js') else 'public, max-age=300')
            self.end_headers(); self.wfile.write(body)
        except OSError: self._send(404, {'ok': False, 'error': 'static file not found'})

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        static = self.STATIC.get(path)
        if static:
            self._send_static(*static); return
        if path in ('/learning','/dashboard-v2','/intelligence-v2'):
            try: self._send(200, dashboard_v2())
            except Exception as exc: self._send(500, {'ok':False,'error':str(exc)[:800]})
            return
        if path == '/lists-369':
            try: self._send(200, lists_369())
            except Exception as exc: self._send(500, {'ok':False,'error':str(exc)[:800]})
            return
        if path == '/calibration':
            self._send(200, calibration_summary()); return
        if path == '/backtest':
            self._send(200, {'results': backtest_point_in_time()}); return
        if path == '/causal':
            self._send(200, graph_summary()); return
        if path.startswith('/causal/'):
            symbol = path.rsplit('/',1)[-1].upper()
            self._send(200, symbol_causal_summary(symbol)); return
        super().do_GET()

    def do_POST(self):
        path = self.path.split('?', 1)[0]
        if path == '/pc-sync':
            if not run_worker._authorized(self):
                self._send(401, {'ok': False, 'error': 'unauthorized'}); return
            data = run_worker._read_json(self); node_id = str(data.get('node_id') or '').strip()
            if not node_id:
                self._send(400, {'ok': False, 'error': 'node_id requerido'}); return
            payload = {
                'node_id': node_id,
                'market_snapshots': list(data.get('market_snapshots') or [])[:500],
                'information_events': list(data.get('information_events') or [])[:500],
                'system_runs': list(data.get('system_runs') or [])[:500],
                'nodes': list(data.get('nodes') or [])[:20],
                'node': {'node_id': node_id, 'node_type': 'desktop', 'name': data.get('name') or 'Windows PC',
                         'enabled': True, 'app_version': data.get('app_version'), 'last_seen': now(),
                         'capabilities': data.get('capabilities') or ['local-collector', 'desktop-ui'],
                         'metadata': {'bridge': 'railway'}},
            }
            try:
                result = forward_supabase(payload, timeout=35); self._send(200, {'ok': True, 'result': result})
            except Exception as exc: self._send(502, {'ok': False, 'error': str(exc)[:800]})
            return
        if path in ('/learning-now','/audit-now'):
            if not run_worker._authorized(self):
                self._send(401, {'ok':False,'error':'unauthorized'}); return
            try:
                result = run_learning_cycle(True) if path == '/learning-now' else audit_system()
                self._send(200, {'ok':True,'result':result})
            except Exception as exc: self._send(500, {'ok':False,'error':str(exc)[:800]})
            return
        super().do_POST()


run_worker._Handler = MobileHandler


def supabase_sync_loop():
    if not supabase_sync_enabled():
        print('[supabase] sync disabled: missing configuration', flush=True); return
    print('[supabase] persistent sync enabled', flush=True)
    while True:
        try:
            result = sync_once(1000)
            print('[supabase] synced market={market} events={events} runs={runs} rep={reputation} alerts={alerts} notifications={notifications} nodes={nodes} agents={agents} positions={positions} trades={trades} marks={marks}'.format(**{k: result.get(k, 0) for k in ('market','events','runs','reputation','alerts','notifications','nodes','agents','positions','trades','marks')}), flush=True)
            write_status(supabase_sync='OK', supabase_market=result.get('market',0), supabase_events=result.get('events',0),
                         supabase_runs=result.get('runs',0), supabase_reputation=result.get('reputation',0),
                         supabase_alerts=result.get('alerts',0), supabase_notifications=result.get('notifications',0),
                         supabase_agents=result.get('agents',0), supabase_trades=result.get('trades',0),
                         supabase_marks=result.get('marks',0), supabase_synced_at=now())
        except Exception as exc:
            print('[supabase] ERROR ' + repr(exc), flush=True); write_status(supabase_sync='ERROR', supabase_sync_error=str(exc)[:500])
        time.sleep(30)


def learning_loop():
    init_learning_db(); next_full = 0; next_eval = 0
    print('[learning] adaptive intelligence enabled; real trading OFF', flush=True)
    while True:
        t=time.time()
        try:
            if t>=next_eval:
                evaluated=evaluate_predictions(); capture_predictions(False); build_causal_graph(168)
                write_status(learning_status='OK', learning_evaluated=evaluated, learning_last_eval=now())
                next_eval=t+1800
            if t>=next_full:
                result=run_learning_cycle(False)
                write_status(learning_status='OK', learning_cycle=result, learning_last_full=now())
                print('[learning] cycle '+json.dumps(result,ensure_ascii=False)[:1800],flush=True)
                next_full=t+21600
        except Exception as exc:
            print('[learning] ERROR '+repr(exc),flush=True); write_status(learning_status='ERROR',learning_error=str(exc)[:700])
        time.sleep(20)


if __name__ == '__main__':
    threading.Thread(target=supabase_sync_loop, name='supabase-sync', daemon=True).start()
    threading.Thread(target=learning_loop, name='learning-engine', daemon=True).start()
    run_worker.main()
