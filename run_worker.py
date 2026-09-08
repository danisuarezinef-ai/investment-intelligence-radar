import json, os, time, traceback, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from radar_core import (init_db,collect_market,collect_sec,collect_science,collect_history,history_ready,write_status,PID,LOG,STATUS,stats,now,profitability_leaders,opportunity_rankings,paper_status,paper_step,con)
from radar_intelligence import (init_intelligence_db,detect_silence,evaluate_source_reputation,list_notifications,mark_notifications_read,source_reputation,silence_alerts,sync_node_heartbeat,sync_nodes,intelligence_summary)
from radar_feeds import collect_news,collect_arxiv
from radar_agents import ensure_agents,agents_status,step_all_agents,reset_agents
from radar_runtime_v2 import safe_fast_cycle,safe_deep_cycle,runtime_snapshot
CONTROL_TOKEN=os.environ.get('RADAR_CONTROL_TOKEN','').strip(); _state_lock=threading.Lock()
def _control_get(key,default=None):
 try:
  init_db(); c=con(); row=c.execute('select value from control where key=?',(key,)).fetchone(); c.close(); return row[0] if row else default
 except Exception:return default
def _control_set(key,value):
 try:
  init_db(); c=con(); c.execute('insert into control(key,value) values(?,?) on conflict(key) do update set value=excluded.value',(key,str(value))); c.commit(); c.close()
 except Exception:pass
_cloud_enabled=str(_control_get('cloud_enabled','1')).lower() not in ('0','false','no','off')
def cloud_enabled():
 with _state_lock:return _cloud_enabled
def set_cloud_enabled(value):
 global _cloud_enabled
 with _state_lock:_cloud_enabled=bool(value)
 _control_set('cloud_enabled','1' if _cloud_enabled else '0'); write_status(cloud_enabled=_cloud_enabled,state='ACTIVO' if _cloud_enabled else 'PAUSADO CLOUD'); return _cloud_enabled
def _read_status():
 try:d=json.load(open(STATUS,'r',encoding='utf-8'))
 except Exception as e:d={'state':'STARTING','heartbeat':None,'detail':str(e)}
 d['cloud_enabled']=cloud_enabled(); return d
def snapshot_payload():
 prices,events,runs,latest,news=stats()
 return {'counts':{'prices':prices,'events':events,'runs':runs},'latest_prices':[{'symbol':r[0],'price':r[1],'source':r[2],'ts':r[3]} for r in latest],'latest_events':[{'source':r[0],'title':r[1],'ts':r[2]} for r in news],'status':_read_status(),'leaders':{'week':profitability_leaders(7),'month':profitability_leaders(30),'year':profitability_leaders(365)},'opportunities':opportunity_rankings(),'paper':paper_status(),'paper_agents':agents_status(),'intelligence':intelligence_summary(),'decision_v2':runtime_snapshot()}
def worker_loop():
 init_db(); init_intelligence_db(); ensure_agents(); open(PID,'w').write(str(os.getpid())); write_status(version='1.4.0',state='INICIANDO',started_at=now(),last_error='',cloud_enabled=cloud_enabled())
 next_market=next_sec=next_science=next_news=next_arxiv=next_silence=next_reputation=next_deep=0; history_attempted=False
 try:
  while True:
   if not cloud_enabled():write_status(state='PAUSADO CLOUD',cloud_enabled=False,current_job=''); time.sleep(2); continue
   t=time.time(); write_status(state='ACTIVO',cloud_enabled=True)
   try:
    if not history_attempted and not history_ready():history_attempted=True; write_status(state='CARGANDO HISTÓRICO',current_job='history'); collect_history()
    if t>=next_market:
     write_status(state='RECOPILANDO MERCADO',current_job='market'); collect_market(); next_market=t+300; paper_step(); agents=step_all_agents(); v2=safe_fast_cycle(); print(f'[paper] agents={len(agents)} champion={v2.get("champion",{}).get("action","?")}',flush=True)
    if t>=next_sec:write_status(state='RECOPILANDO SEC',current_job='sec'); collect_sec(); next_sec=t+900
    if t>=next_science:write_status(state='RECOPILANDO CIENCIA',current_job='science'); collect_science(); next_science=t+1800
    if t>=next_news:write_status(state='RECOPILANDO NOTICIAS',current_job='news'); collect_news(); next_news=t+900
    if t>=next_arxiv:write_status(state='RECOPILANDO ARXIV',current_job='arxiv'); collect_arxiv(); next_arxiv=t+3600
    if t>=next_silence:write_status(state='ANALIZANDO SILENCIO',current_job='silence'); detect_silence(); next_silence=t+300
    if t>=next_reputation:write_status(state='EVALUANDO FUENTES',current_job='source_reputation'); evaluate_source_reputation(); next_reputation=t+21600
    if t>=next_deep:write_status(state='APRENDIZAJE PROFUNDO',current_job='decision_v2'); safe_deep_cycle(); next_deep=t+21600
   except Exception as e:
    open(LOG,'a',encoding='utf-8').write(traceback.format_exc()+'\n'); write_status(state='ERROR',last_error=str(e))
   write_status(state='ESPERANDO SIGUIENTE CICLO',current_job='',cloud_enabled=True); time.sleep(10)
 finally:
  try:os.remove(PID)
  except OSError:pass
def _authorized(h):return bool(CONTROL_TOKEN) and h.headers.get('Authorization','')=='Bearer '+CONTROL_TOKEN
def _read_json(h):
 try:n=int(h.headers.get('Content-Length','0') or 0); return json.loads(h.rfile.read(n).decode()) if n else {}
 except Exception:return {}
class _Handler(BaseHTTPRequestHandler):
 def _send(self,code,payload):
  body=json.dumps(payload,ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type'); self.end_headers(); self.wfile.write(body)
 def do_OPTIONS(self):self.send_response(204); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type'); self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS'); self.end_headers()
 def do_GET(self):
  p=self.path.split('?',1)[0]
  routes={'/snapshot':snapshot_payload,'/mobile/dashboard':snapshot_payload,'/decision-v2':runtime_snapshot}
  if p=='/health':return self._send(200,{'ok':True,'service':'Investment Intelligence Radar Cloud','version':'1.4.0','cloud_enabled':cloud_enabled(),'status':_read_status(),'decision_v2':runtime_snapshot()})
  if p=='/status':return self._send(200,_read_status())
  if p in routes:return self._send(200,routes[p]())
  if p=='/notifications':return self._send(200,{'notifications':list_notifications(100,False)})
  if p=='/source-reputation':return self._send(200,{'sources':source_reputation(100)})
  if p=='/silence-alerts':return self._send(200,{'alerts':silence_alerts(100,True)})
  if p=='/nodes':return self._send(200,{'nodes':sync_nodes(100)})
  if p=='/paper-agents':return self._send(200,{'agents':agents_status()})
  self._send(404,{'ok':False,'error':'not found'})
 def do_POST(self):
  p=self.path.split('?',1)[0]
  if not _authorized(self):return self._send(401,{'ok':False,'error':'unauthorized'})
  if p=='/toggle':return self._send(200,{'ok':True,'cloud_enabled':set_cloud_enabled(not cloud_enabled()),'status':_read_status()})
  if p=='/decision-v2/fast':return self._send(200,safe_fast_cycle())
  if p=='/decision-v2/deep':return self._send(200,safe_deep_cycle())
  if p=='/collect-now':
   if not history_ready():collect_history()
   results={'market':collect_market(),'sec':collect_sec(),'science':collect_science(),'news':collect_news(),'arxiv':collect_arxiv(),'silence':len(detect_silence()),'source_reputation':len(evaluate_source_reputation())}; paper_step(force=True); results['paper_agents']=len(step_all_agents(force=True)); results['decision_v2']=safe_fast_cycle(); return self._send(200,{'ok':True,'results':results,'snapshot':snapshot_payload()})
  if p=='/paper-agents/step':return self._send(200,{'ok':True,'agents':step_all_agents(force=True),'decision_v2':safe_fast_cycle()})
  if p=='/paper-agents/reset':return self._send(200,{'ok':True,'agents':reset_agents(float(_read_json(self).get('initial_cash',200.0)))})
  self._send(404,{'ok':False,'error':'not found'})
 def log_message(self,fmt,*args):pass
def main():
 port=os.environ.get('PORT')
 if port:threading.Thread(target=worker_loop,daemon=True).start(); ThreadingHTTPServer(('0.0.0.0',int(port)),_Handler).serve_forever()
 else:worker_loop()
if __name__=='__main__':main()
