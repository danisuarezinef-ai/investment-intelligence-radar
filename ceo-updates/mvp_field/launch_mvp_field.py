from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.mvp_field_first_real_goal import DEFAULT_SPEC, MVPFieldRunner, SingleGeminiProvider

RESULTS = ROOT / "RESULTADOS_CEO"
RESULTS.mkdir(parents=True, exist_ok=True)

HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CEO de IAs · MVP FIELD</title>
<style>
:root{font-family:Inter,Segoe UI,system-ui,sans-serif;background:#f4f6f8;color:#111827}
body{margin:0}main{max-width:860px;margin:auto;padding:28px 18px 60px}
.card{background:white;border:1px solid #dde3eb;border-radius:18px;padding:20px;margin:14px 0;box-shadow:0 8px 28px rgba(20,32,48,.06)}
h1{font-size:32px;margin:6px 0 10px}h2{font-size:17px;margin:0 0 8px}.muted{color:#667085}.goal{line-height:1.5;background:#f7f9fc;border-radius:12px;padding:14px}
.badge{display:inline-block;padding:7px 11px;border-radius:999px;font-weight:800;font-size:12px;background:#eef2f6}
.pass{background:#e8f7ed;color:#166534}.fail{background:#fff0ec;color:#9b2c20}.run{background:#eef4ff;color:#1d4ed8}
button{border:0;border-radius:12px;padding:11px 16px;background:#111827;color:white;font-weight:800;cursor:pointer}button:disabled{opacity:.45;cursor:default}
pre{white-space:pre-wrap;word-break:break-word;background:#f7f9fc;border-radius:12px;padding:12px;font-size:12px}
a{color:#1d4ed8;font-weight:700}.metric{font-size:42px;font-weight:900;margin:8px 0}.steps{display:grid;gap:7px}.step{display:flex;justify-content:space-between;gap:10px;background:#f7f9fc;padding:9px 11px;border-radius:10px}
</style></head>
<body><main>
<div class="muted">CEO DE IAs · modo temporal de campo</div>
<h1>FIRST REAL GOAL</h1>
<div class="card"><h2>Único objetivo</h2><div class="goal" id="goal"></div></div>
<div class="card"><h2>Única métrica</h2><div id="metric" class="metric">—</div><div id="metricText" class="muted">Todavía no ejecutado.</div></div>
<div class="card">
  <button id="start" onclick="start()">Ejecutar FIELD-MVP-01</button>
  <span id="status" class="badge">IDLE</span>
  <div id="detail" class="muted" style="margin-top:12px"></div>
  <div id="resultLink" style="margin-top:12px"></div>
</div>
<div class="card"><h2>Camino mínimo</h2><div id="steps" class="steps"></div></div>
<div class="card"><h2>Reglas activas</h2><div class="muted">1 proveedor · máximo 1 retry · máximo 6 pasos · sin scheduler complejo · sin recovery/integrity/continuity audits · cierre sólo por entregable verificado.</div></div>
</main>
<script>
const goal = __GOAL_JSON__;
document.getElementById('goal').textContent=goal;
async function j(u,o){const r=await fetch(u,o);const x=await r.json();if(!r.ok)throw new Error(x.error||('HTTP '+r.status));return x}
function render(s){
 const m=document.getElementById('metric'),mt=document.getElementById('metricText'),st=document.getElementById('status'),d=document.getElementById('detail'),b=document.getElementById('start');
 if(s.delivery_pass===true){m.textContent='PASS';m.className='metric pass';mt.textContent='Entregable correcto + verificación independiente + objetivo cerrado.'}
 else if(s.delivery_pass===false){m.textContent='FAIL';m.className='metric fail';mt.textContent='No se cerró el objetivo.'}
 else {m.textContent='—';m.className='metric';mt.textContent=s.status==='running'?'Ejecutando camino feliz mínimo.':'Todavía no ejecutado.'}
 st.textContent=(s.status||'idle').toUpperCase()+' · '+(s.stage||'idle');st.className='badge '+(s.delivery_pass===true?'pass':s.delivery_pass===false?'fail':s.status==='running'?'run':'');
 d.textContent=s.failure_reason||('Salida: '+(s.output_path||''));
 b.disabled=s.status==='running'||s.delivery_pass===true;
 const rows=s.steps||[];document.getElementById('steps').innerHTML=rows.length?rows.map(x=>'<div class="step"><strong>'+x.name+'</strong><span>'+x.status+(x.attempts?' · intento '+x.attempts:'')+'</span></div>').join(''):'<div class="muted">Sin pasos ejecutados.</div>';
 document.getElementById('resultLink').innerHTML=s.delivery_pass===true?'<a href="/result" target="_blank">Abrir FIELD_MVP_01.md</a>':'';
}
async function refresh(){try{render(await j('/state'))}catch(e){document.getElementById('detail').textContent=e.message}}
async function start(){try{document.getElementById('start').disabled=true;render(await j('/start',{method:'POST'}))}catch(e){document.getElementById('detail').textContent=e.message;document.getElementById('start').disabled=false}}
setInterval(refresh,700);refresh();
</script></body></html>"""


def _secret_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "CEO de IAs" / "secrets" / "gemini_api_key.dpapi"


def _dpapi_unprotect(blob: bytes) -> str | None:
    if sys.platform != "win32" or not blob:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(DATA_BLOB),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        entropy_raw = b"CEO-de-IAs|Gemini|DPAPI|v1"
        blob_buf = ctypes.create_string_buffer(blob, len(blob))
        entropy_buf = ctypes.create_string_buffer(entropy_raw, len(entropy_raw))
        in_blob = DATA_BLOB(len(blob), ctypes.cast(blob_buf, ctypes.POINTER(ctypes.c_byte)))
        entropy_blob = DATA_BLOB(len(entropy_raw), ctypes.cast(entropy_buf, ctypes.POINTER(ctypes.c_byte)))
        out_blob = DATA_BLOB()
        description = ctypes.c_void_p()
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), ctypes.byref(description), ctypes.byref(entropy_blob),
            None, None, 0, ctypes.byref(out_blob),
        )
        if not ok:
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
        finally:
            if description.value:
                kernel32.LocalFree(description)
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))
    except Exception:
        return None


def load_stored_gemini_key() -> str | None:
    path = _secret_path()
    if not path.is_file():
        return None
    raw = path.read_bytes()
    candidates = [raw]
    try:
        candidates.append(base64.b64decode(raw.decode("ascii").strip(), validate=True))
    except Exception:
        pass
    for candidate in candidates:
        plain = _dpapi_unprotect(candidate)
        if plain:
            key = plain.strip().strip("\"'").strip()
            if 20 <= len(key) <= 256 and not any(ch.isspace() for ch in key):
                return key
    return None


class App:
    def __init__(self) -> None:
        self.key = load_stored_gemini_key()
        self.runner: MVPFieldRunner | None = None
        self.thread: threading.Thread | None = None
        self.lock = threading.Lock()

    def state(self) -> dict:
        with self.lock:
            if self.runner is None:
                return {
                    "mode": "MVP_FIELD",
                    "goal_id": DEFAULT_SPEC.goal_id,
                    "goal": DEFAULT_SPEC.objective,
                    "status": "idle" if self.key else "blocked",
                    "stage": "ready" if self.key else "missing_stored_key",
                    "delivery_pass": None,
                    "failure_reason": "" if self.key else "No se encontró la clave Gemini DPAPI ya guardada. MVP_FIELD no crea ni reemplaza claves.",
                    "output_path": str(RESULTS / DEFAULT_SPEC.output_name),
                    "steps": [],
                }
            return dict(self.runner.snapshot())

    def start(self) -> dict:
        with self.lock:
            if not self.key:
                raise RuntimeError("No se encontró una clave Gemini guardada; MVP_FIELD no crea una nueva.")
            current = self.runner.snapshot() if self.runner else {}
            if current.get("status") == "running":
                return dict(current)
            if current.get("delivery_pass") is True:
                return dict(current)
            self.runner = MVPFieldRunner(
                provider_factory=lambda: SingleGeminiProvider(self.key or "", model="auto", timeout_seconds=90),
                results_root=RESULTS,
            )
            runner = self.runner

        def _work():
            asyncio.run(runner.run())

        self.thread = threading.Thread(target=_work, name="ceo-mvp-field-goal", daemon=True)
        self.thread.start()
        return self.state()


APP = App()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def _json(self, row: dict, code: int = 200):
        raw = json.dumps(row, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            text = HTML.replace("__GOAL_JSON__", json.dumps(DEFAULT_SPEC.objective, ensure_ascii=False))
            raw = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if path == "/state":
            return self._json(APP.state())
        if path == "/result":
            target = RESULTS / DEFAULT_SPEC.output_name
            if not target.is_file():
                return self._json({"error": "result_not_available"}, 404)
            raw = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Disposition", f'inline; filename="{DEFAULT_SPEC.output_name}"')
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        return self._json({"error": "not_found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/start":
            try:
                return self._json(APP.start())
            except Exception as exc:
                return self._json({"error": f"{type(exc).__name__}: {exc}"}, 409)
        return self._json({"error": "not_found"}, 404)


def choose_port() -> int:
    for port in range(8791, 8797):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No hay puerto libre para MVP_FIELD (8791-8796)")


def open_app(url: str) -> None:
    if os.environ.get("CEO_NO_BROWSER") == "1":
        return
    candidates = [
        os.environ.get("PROGRAMFILES", "") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES(X86)", "") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES", "") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("PROGRAMFILES(X86)", "") + r"\Microsoft\Edge\Application\msedge.exe",
    ]
    for raw in candidates:
        path = Path(raw)
        if raw and path.is_file():
            try:
                subprocess.Popen([str(path), f"--app={url}", "--start-maximized"], close_fds=True)
                return
            except Exception:
                pass
    webbrowser.open(url)


def main() -> int:
    port = choose_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    threading.Timer(0.5, lambda: open_app(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
