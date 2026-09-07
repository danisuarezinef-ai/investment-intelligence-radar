import json, os, time, traceback, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from radar_core import init_db, collect_market, collect_sec, collect_science, write_status, PID, LOG, STATUS, stats, now, profitability_leaders, opportunity_rankings, paper_status, paper_step

CONTROL_TOKEN=os.environ.get('RADAR_CONTROL_TOKEN','').strip(); _cloud_enabled=True; _state_lock=threading.Lock()
def cloud_enabled():
    with _state_lock:return _cloud_enabled
def set_cloud_enabled(value):
    global _cloud_enabled
    with _state_lock:_cloud_enabled=bool(value)
    write_status(cloud_enabled=_cloud_enabled,state='ACTIVO' if _cloud_enabled else 'PAUSADO CLOUD'); return _cloud_enabled

def _read_status():
    try:
        with open(STATUS,'r',encoding='utf-8') as f:d=json.load(f)
    except Exception as e:d={'state':'STARTING','heartbeat':None,'detail':str(e)}
    d['cloud_enabled']=cloud_enabled(); return d

def snapshot_payload():
    prices,events,runs,latest,news=stats()
    return {'counts':{'prices':prices,'events':events,'runs':runs},'latest_prices':[{'symbol':r[0],'price':r[1],'source':r[2],'ts':r[3]} for r in latest],'latest_events':[{'source':r[0],'title':r[1],'ts':r[2]} for r in news],'status':_read_status(),'leaders':{'week':profitability_leaders(7),'month':profitability_leaders(30),'year':profitability_leaders(365)},'opportunities':opportunity_rankings(),'paper':paper_status()}

def worker_loop():
    init_db(); open(PID,'w').write(str(os.getpid())); write_status(version='1.2.0',state='INICIANDO',started_at=now(),last_error='',cloud_enabled=True)
    next_market=next_sec=next_science=0
    try:
        while True:
            if not cloud_enabled():write_status(state='PAUSADO CLOUD',cloud_enabled=False,current_job=''); time.sleep(2); continue
            t=time.time(); write_status(state='ACTIVO',cloud_enabled=True)
            try:
                if t>=next_market:
                    write_status(state='RECOPILANDO MERCADO',current_job='market'); n=collect_market(); print(f'[collector] market added={n}',flush=True); next_market=t+300; paper_step()
                if t>=next_sec:
                    write_status(state='RECOPILANDO SEC',current_job='sec'); n=collect_sec(); print(f'[collector] sec added={n}',flush=True); next_sec=t+900
                if t>=next_science:
                    write_status(state='RECOPILANDO CIENCIA',current_job='science'); n=collect_science(); print(f'[collector] science added={n}',flush=True); next_science=t+1800
                p,e,r,_,_=stats(); print(f'[collector] totals prices={p} events={e} runs={r}',flush=True)
            except Exception as e:
                with open(LOG,'a',encoding='utf-8') as f:f.write(traceback.format_exc()+'\n')
                print('[collector] ERROR '+repr(e),flush=True); write_status(state='ERROR',last_error=str(e))
            write_status(state='ESPERANDO SIGUIENTE CICLO',current_job='',cloud_enabled=True); time.sleep(10)
    finally:
        try:os.remove(PID)
        except OSError:pass

def _authorized(h):return bool(CONTROL_TOKEN) and h.headers.get('Authorization','')=='Bearer '+CONTROL_TOKEN
class _Handler(BaseHTTPRequestHandler):
    def _send(self,code,payload):
        body=json.dumps(payload,ensure_ascii=False).encode('utf-8'); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/health':self._send(200,{'ok':True,'service':'Investment Intelligence Radar Cloud','cloud_enabled':cloud_enabled(),'status':_read_status()}); return
        if path=='/status':self._send(200,_read_status()); return
        if path=='/snapshot':self._send(200,snapshot_payload()); return
        self._send(404,{'ok':False,'error':'not found'})
    def do_POST(self):
        path=self.path.split('?',1)[0]
        if not _authorized(self):self._send(401,{'ok':False,'error':'unauthorized'}); return
        if path=='/toggle':self._send(200,{'ok':True,'cloud_enabled':set_cloud_enabled(not cloud_enabled()),'status':_read_status()}); return
        if path=='/collect-now':
            results={'market':collect_market(),'sec':collect_sec(),'science':collect_science()}; paper_step(force=True); self._send(200,{'ok':True,'results':results,'snapshot':snapshot_payload()}); return
        self._send(404,{'ok':False,'error':'not found'})
    def log_message(self,fmt,*args):print('[http]',fmt % args,flush=True)
def main():
    port=os.environ.get('PORT')
    if port:
        threading.Thread(target=worker_loop,name='radar-worker',daemon=True).start(); p=int(port); print(f'Radar cloud HTTP listening on 0.0.0.0:{p}',flush=True); ThreadingHTTPServer(('0.0.0.0',p),_Handler).serve_forever()
    else:worker_loop()
if __name__=='__main__':main()
