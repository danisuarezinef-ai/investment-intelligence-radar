import json
import os
import sqlite3
import threading
import time
import urllib.parse

import run_worker
from radar_core import con, fetch, init_db, log, now
from radar_status_safe import install as install_safe_status
from radar_supabase_sync import enabled as supabase_sync_enabled, sync_once, _post as forward_supabase
from radar_learning_sync import enabled as learning_sync_enabled, sync_learning_once
from radar_learning import init_learning_db, capture_predictions, evaluate_predictions, backtest_point_in_time, calibration_summary
from radar_learning_guarded import run_guarded_cycle, learning_health
from radar_historical_lab import run_historical_lab, historical_lab_health, init_historical_lab_db
from radar_brain_evolution import init_brain_db, brain_dashboard
from radar_dashboard_v2 import dashboard_payload as intelligence_dashboard
from radar_causal import build_causal_graph, graph_summary, symbol_causal_summary
from radar_benchmark import benchmark_agents
from radar_scoring_v2 import lists_369_v2, multihorizon_rankings
from radar_reputation_v2 import evaluate_source_dimensions, top_source_dimensions
from radar_audit_v15 import run_integrity_audit

write_status=install_safe_status(run_worker)


def collect_science_safe():
    init_db();query='artificial intelligence OR semiconductor OR battery OR fusion energy OR quantum computing'
    params=urllib.parse.urlencode({'query':query,'format':'json','pageSize':15});url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+params
    if any(ord(ch)<32 for ch in url):raise RuntimeError('Europe PMC URL contains control characters')
    added=0;seen=0
    try:
        data=json.loads(fetch(url,25,{'Accept':'application/json'}));results=(data.get('resultList') or {}).get('result') or [];seen=len(results);c=con()
        try:
            for item in results:
                title=' '.join(str(item.get('title') or '').split());pid=item.get('pmid') or item.get('pmcid') or item.get('id')
                if not title or not pid:continue
                article_url='https://europepmc.org/article/MED/'+urllib.parse.quote(str(pid),safe='')
                try:c.execute('insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)',(now(),'Europe PMC',title,article_url,'science'));added+=1
                except sqlite3.IntegrityError:pass
            c.commit()
        finally:c.close()
        log('science','OK',f'{added} eventos nuevos de {seen} recuperados');write_status(science_status='OK',science_seen=seen,last_error='')
    except Exception as exc:log('science','ERROR',str(exc));write_status(science_status='ERROR',last_error=str(exc))
    return added

run_worker.collect_science=collect_science_safe
BaseHandler=run_worker._Handler

class MobileHandler(BaseHandler):
    STATIC={'/':('mobile/index.html','text/html; charset=utf-8'),'/mobile':('mobile/index.html','text/html; charset=utf-8'),'/mobile/':('mobile/index.html','text/html; charset=utf-8'),'/mobile/index.html':('mobile/index.html','text/html; charset=utf-8'),'/mobile/manifest.webmanifest':('mobile/manifest.webmanifest','application/manifest+json; charset=utf-8'),'/mobile/sw.js':('mobile/sw.js','application/javascript; charset=utf-8')}
    def _send_static(self,relpath,content_type):
        path=os.path.join(os.path.dirname(__file__),relpath)
        try:
            with open(path,'rb') as f:body=f.read()
            self.send_response(200);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-cache' if relpath.endswith('sw.js') else 'public, max-age=300');self.end_headers();self.wfile.write(body)
        except OSError:self._send(404,{'ok':False,'error':'static file not found'})
    def do_GET(self):
        path=self.path.split('?',1)[0];static=self.STATIC.get(path)
        if static:self._send_static(*static);return
        if path in ('/learning','/dashboard-v2','/intelligence-v2'):
            try:
                payload=intelligence_dashboard();payload['historical_lab']=historical_lab_health(8);payload['brain_evolution']=brain_dashboard(30);self._send(200,payload)
            except Exception as exc:self._send(500,{'ok':False,'error':str(exc)[:800]})
            return
        if path=='/brain-evolution':
            try:self._send(200,brain_dashboard(100))
            except Exception as exc:self._send(500,{'ok':False,'error':str(exc)[:800]})
            return
        if path=='/learning-health':
            try:
                payload=learning_health();payload['historical_lab']=historical_lab_health(8);payload['brain_evolution']=brain_dashboard(30);self._send(200,payload)
            except Exception as exc:self._send(500,{'ok':False,'error':str(exc)[:800]})
            return
        if path=='/historical-lab':
            try:self._send(200,historical_lab_health(20))
            except Exception as exc:self._send(500,{'ok':False,'error':str(exc)[:800]})
            return
        if path=='/lists-369':
            try:self._send(200,lists_369_v2())
            except Exception as exc:self._send(500,{'ok':False,'error':str(exc)[:800]})
            return
        if path=='/scoring-v2':
            try:self._send(200,multihorizon_rankings())
            except Exception as exc:self._send(500,{'ok':False,'error':str(exc)[:800]})
            return
        if path=='/benchmarks':self._send(200,{'agents':benchmark_agents()});return
        if path=='/source-reputation-v2':self._send(200,{'sources':top_source_dimensions(100)});return
        if path=='/calibration':self._send(200,calibration_summary());return
        if path=='/backtest':self._send(200,{'results':backtest_point_in_time()});return
        if path=='/causal':self._send(200,graph_summary());return
        if path.startswith('/causal/'):self._send(200,symbol_causal_summary(path.rsplit('/',1)[-1].upper()));return
        super().do_GET()
    def do_POST(self):
        path=self.path.split('?',1)[0]
        if path=='/pc-sync':
            if not run_worker._authorized(self):self._send(401,{'ok':False,'error':'unauthorized'});return
            data=run_worker._read_json(self);node_id=str(data.get('node_id') or '').strip()
            if not node_id:self._send(400,{'ok':False,'error':'node_id requerido'});return
            payload={'node_id':node_id,'market_snapshots':list(data.get('market_snapshots') or [])[:500],'information_events':list(data.get('information_events') or [])[:500],'system_runs':list(data.get('system_runs') or [])[:500],'nodes':list(data.get('nodes') or [])[:20],'node':{'node_id':node_id,'node_type':'desktop','name':data.get('name') or 'Windows PC','enabled':True,'app_version':data.get('app_version'),'last_seen':now(),'capabilities':data.get('capabilities') or ['local-collector','desktop-ui'],'metadata':{'bridge':'railway'}}}
            try:self._send(200,{'ok':True,'result':forward_supabase(payload,timeout=35)})
            except Exception as exc:self._send(502,{'ok':False,'error':str(exc)[:800]})
            return
        if path in ('/learning-now','/audit-now','/historical-lab-now'):
            if not run_worker._authorized(self):self._send(401,{'ok':False,'error':'unauthorized'});return
            try:
                if path=='/learning-now':
                    result=run_guarded_cycle(True);result['causal_edges_created']=build_causal_graph(168);result['source_dimensions']=len(evaluate_source_dimensions());result['audit_v15']=run_integrity_audit()['summary']
                elif path=='/historical-lab-now':result=run_historical_lab(promote=True)
                else:result=run_integrity_audit()
                self._send(200,{'ok':True,'result':result})
            except Exception as exc:self._send(500,{'ok':False,'error':str(exc)[:800]})
            return
        super().do_POST()
run_worker._Handler=MobileHandler


def supabase_sync_loop():
    if not supabase_sync_enabled():print('[supabase] sync disabled: missing configuration',flush=True);return
    print('[supabase] persistent sync enabled',flush=True)
    while True:
        try:
            result=sync_once(1000);print('[supabase] synced market={market} events={events} runs={runs} rep={reputation} alerts={alerts} notifications={notifications} nodes={nodes} agents={agents} positions={positions} trades={trades} marks={marks}'.format(**{k:result.get(k,0) for k in ('market','events','runs','reputation','alerts','notifications','nodes','agents','positions','trades','marks')}),flush=True)
            write_status(supabase_sync='OK',supabase_market=result.get('market',0),supabase_events=result.get('events',0),supabase_runs=result.get('runs',0),supabase_reputation=result.get('reputation',0),supabase_alerts=result.get('alerts',0),supabase_notifications=result.get('notifications',0),supabase_agents=result.get('agents',0),supabase_trades=result.get('trades',0),supabase_marks=result.get('marks',0),supabase_synced_at=now())
        except Exception as exc:print('[supabase] ERROR '+repr(exc),flush=True);write_status(supabase_sync='ERROR',supabase_sync_error=str(exc)[:500])
        time.sleep(30)


def learning_sync_loop():
    if not learning_sync_enabled():print('[learning-sync] disabled: missing configuration',flush=True);return
    print('[learning-sync] persistent model history enabled',flush=True)
    while True:
        try:
            r=sync_learning_once(750);print('[learning-sync] '+json.dumps({k:v for k,v in r.items() if k!='remote'},ensure_ascii=False),flush=True);write_status(learning_persistence='OK',learning_persisted_at=now())
        except Exception as exc:print('[learning-sync] ERROR '+repr(exc),flush=True);write_status(learning_persistence='ERROR',learning_persistence_error=str(exc)[:600])
        time.sleep(45)


def learning_loop():
    init_learning_db();init_historical_lab_db();init_brain_db();next_eval=time.time()+15;next_full=time.time()+25;next_hist=time.time()+40
    print('[learning] live + evolutionary historical champion/challenger + epistemic brain layer enabled; real trading OFF',flush=True)
    while True:
        t=time.time()
        try:
            if t>=next_eval:
                evaluated=evaluate_predictions();created=capture_predictions(False);edges=build_causal_graph(168);write_status(learning_status='OK',learning_evaluated=evaluated,learning_predictions=created,causal_edges_created=edges,learning_last_eval=now());next_eval=t+1800
            if t>=next_full:
                result=run_guarded_cycle(False);dims=evaluate_source_dimensions();audit=run_integrity_audit();bench=benchmark_agents();write_status(learning_status='OK',learning_cycle=result,source_dimensions=len(dims),audit_v15=audit['summary'],benchmark_agents=len(bench),learning_last_full=now());print('[learning] guarded live cycle '+json.dumps({'core':result,'source_dimensions':len(dims),'audit':audit['summary'],'benchmarks':len(bench)},ensure_ascii=False)[:2600],flush=True);next_full=t+21600
            if t>=next_hist:
                hist=run_historical_lab(promote=True);write_status(historical_lab='OK',historical_lab_last=hist,historical_lab_at=now());print('[historical-lab] '+json.dumps(hist,ensure_ascii=False)[:2600],flush=True);next_hist=t+43200
        except Exception as exc:print('[learning] ERROR '+repr(exc),flush=True);write_status(learning_status='ERROR',learning_error=str(exc)[:700]);next_hist=max(next_hist,time.time()+1800)
        time.sleep(20)

if __name__=='__main__':
    threading.Thread(target=supabase_sync_loop,name='supabase-sync',daemon=True).start();threading.Thread(target=learning_sync_loop,name='learning-sync',daemon=True).start();threading.Thread(target=learning_loop,name='learning-engine',daemon=True).start();run_worker.main()
