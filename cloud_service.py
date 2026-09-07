import json
import os
import sqlite3
import urllib.parse

import run_worker
from radar_core import con, fetch, init_db, log, now, write_status


def collect_science_safe():
    """Europe PMC collector with fully encoded query parameters and no control characters."""
    init_db()
    query = 'artificial intelligence OR semiconductor OR battery OR fusion energy OR quantum computing'
    params = urllib.parse.urlencode({
        'query': query,
        'format': 'json',
        'pageSize': 15,
    })
    url = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?' + params
    if any(ord(ch) < 32 for ch in url):
        raise RuntimeError('Europe PMC URL contains control characters')

    added = 0
    seen = 0
    try:
        data = json.loads(fetch(url, 25, {'Accept': 'application/json'}))
        results = (data.get('resultList') or {}).get('result') or []
        seen = len(results)
        c = con()
        try:
            for item in results:
                title = ' '.join(str(item.get('title') or '').split())
                pid = item.get('pmid') or item.get('pmcid') or item.get('id')
                if not title or not pid:
                    continue
                article_url = 'https://europepmc.org/article/MED/' + urllib.parse.quote(str(pid), safe='')
                try:
                    c.execute(
                        'insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)',
                        (now(), 'Europe PMC', title, article_url, 'science'),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    pass
            c.commit()
        finally:
            c.close()
        log('science', 'OK', f'{added} eventos nuevos de {seen} recuperados')
        write_status(science_status='OK', science_seen=seen, last_error='')
    except Exception as exc:
        log('science', 'ERROR', str(exc))
        write_status(science_status='ERROR', last_error=str(exc))
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
            with open(path, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-cache' if relpath.endswith('sw.js') else 'public, max-age=300')
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            self._send(404, {'ok': False, 'error': 'static file not found'})

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        static = self.STATIC.get(path)
        if static:
            self._send_static(*static)
            return
        super().do_GET()


run_worker._Handler = MobileHandler


if __name__ == '__main__':
    run_worker.main()
