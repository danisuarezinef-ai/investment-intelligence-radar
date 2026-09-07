import json, os, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from radar_core import STATUS, stats, init_db
from run_worker import main as worker_main

PORT = int(os.environ.get('PORT', '8080'))


def read_status():
    try:
        with open(STATUS, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {'state': 'STARTING', 'heartbeat': None, 'detail': str(e)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/health':
            s = read_status()
            self._send(200, {'ok': True, 'service': 'Investment Intelligence Radar Cloud', 'status': s})
            return
        if path == '/status':
            self._send(200, read_status())
            return
        if path == '/snapshot':
            prices, events, runs, latest, news = stats()
            self._send(200, {
                'counts': {'prices': prices, 'events': events, 'runs': runs},
                'latest_prices': [
                    {'symbol': r[0], 'price': r[1], 'source': r[2], 'ts': r[3]} for r in latest
                ],
                'latest_events': [
                    {'source': r[0], 'title': r[1], 'ts': r[2]} for r in news
                ],
                'status': read_status(),
            })
            return
        self._send(404, {'ok': False, 'error': 'not found'})

    def log_message(self, fmt, *args):
        print('[http]', fmt % args, flush=True)


def main():
    init_db()
    t = threading.Thread(target=worker_main, name='radar-worker', daemon=True)
    t.start()
    print(f'Radar cloud HTTP listening on 0.0.0.0:{PORT}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
