#!/usr/bin/env python3
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse, hashlib, hmac, json, os, sys, traceback

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from ceo_core.mobile_node import MobileNodeConfig, MobileNodeCore, _json_bytes


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--host',default=os.getenv('CEO_MOBILE_BIND','0.0.0.0'));ap.add_argument('--port',type=int,default=int(os.getenv('CEO_MOBILE_PORT','8765')));args=ap.parse_args()
    cfg=MobileNodeConfig(bind_host=args.host,port=args.port);core=MobileNodeCore(cfg);secret=os.getenv(cfg.shared_secret_env,'')
    if not secret:
        print(f'[BLOCKED] define {cfg.shared_secret_env} before exposing mobile node');return 2
    class H(BaseHTTPRequestHandler):
        server_version='CEOMobile/1'
        def send_json(self,code,row):
            raw=json.dumps(row,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def auth(self,raw):
            sig=self.headers.get('X-CEO-Signature','');exp=hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest();return hmac.compare_digest(sig,exp)
        def do_GET(self):
            if self.path=='/':
                d=core.dashboard();html=f'''<!doctype html><meta name=viewport content="width=device-width"><title>CEO Mobile</title><style>body{{font-family:sans-serif;max-width:700px;margin:2rem auto;padding:0 1rem}}pre{{white-space:pre-wrap}}.bad{{color:#a00}}.ok{{color:#080}}</style><h1>CEO Mobile Node</h1><p>Emergency stop: <b class={'bad' if d['emergency_stop'] else 'ok'}>{d['emergency_stop']}</b></p><p>Queued jobs: {d['jobs']['queued']} · Pending approvals: {d['approvals']['pending']}</p><p>Local model healthy: {d['local_model']['healthy']}</p><p>Auto-spend allowed: <b>{d['spend_policy']['auto_spend_allowed']}</b></p><pre>{json.dumps(d,indent=2,ensure_ascii=False)}</pre>''';raw=html.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
            if self.path=='/health':return self.send_json(200,{'ok':True,'node_id':cfg.node_id,'emergency_stop':core.emergency_active()})
            if self.path=='/preflight':return self.send_json(200,vars(core.preflight.snapshot()))
            if self.path=='/dashboard':return self.send_json(200,core.dashboard())
            if self.path=='/approvals':return self.send_json(200,{'pending':core.approvals.pending()})
            if self.path=='/certification':return self.send_json(200,core.certification())
            return self.send_json(404,{'error':'not found'})
        def do_POST(self):
            n=int(self.headers.get('Content-Length','0') or 0);raw=self.rfile.read(n)
            if not self.auth(raw):return self.send_json(401,{'error':'invalid signature'})
            try:body=json.loads(raw.decode() or '{}')
            except Exception:return self.send_json(400,{'error':'invalid json'})
            try:
                if self.path=='/worker':
                    if core.emergency_active():return self.send_json(423,{'success':False,'error':'emergency stop active'})
                    instr=body.get('instruction') or body.get('work_unit',{}).get('description') or body.get('work_unit',{}).get('title') or ''
                    row=core.worker.execute(str(instr),body.get('context',{}));return self.send_json(200,{'success':True,'text':row['text'],'metadata':row})
                if self.path=='/jobs':return self.send_json(200,core.queue.enqueue(body.get('kind','generic'),body.get('payload',{}),priority=int(body.get('priority',50))))
                if self.path=='/emergency-stop':return self.send_json(200,core.emergency_stop(str(body.get('reason','remote human stop'))))
                if self.path=='/approval/request':return self.send_json(200,core.approvals.request(str(body.get('action','unknown')),body.get('payload',{}),risk=str(body.get('risk','normal'))))
                return self.send_json(404,{'error':'not found'})
            except Exception as exc:return self.send_json(500,{'error':f'{type(exc).__name__}: {exc}'})
        def log_message(self,fmt,*args):print('[mobile-http]',fmt%args)
    srv=ThreadingHTTPServer((args.host,args.port),H);print(f'CEO Mobile Node listening on http://{args.host}:{args.port}');srv.serve_forever()
    return 0
if __name__=='__main__':raise SystemExit(main())
