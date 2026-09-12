"""Production entrypoint v7: v6 plus tasks 201-270.

Read-only audit/governance orchestration. Windows remains 1.5.28 and REAL_TRADING=false.
Heavy v6 evidence collection is background-only: HTTP handlers never synchronously
trigger a cold evidence rebuild.
"""
from __future__ import annotations
import os,threading,time
from collections import defaultdict,deque

import cloud_service_v6 as base6
from radar_pre160_cache_v7 import AsyncSnapshotCache
from radar_pre160_controls_v7 import build_matrix_201_270
from radar_pre160_data_authority_v7 import content_hash

REAL_TRADING=False
_CACHE=AsyncSnapshotCache(ttl_seconds=60,stale_seconds=300)
_LATENCY=defaultdict(lambda:deque(maxlen=120))
_PREWARM_STARTED=False
_PREWARM_LOCK=threading.Lock()

def _p95(values):
    xs=sorted(float(x) for x in values)
    if not xs:return None
    return xs[min(len(xs)-1,max(0,int(round(.95*(len(xs)-1)))))]

def deployment_identity():
    sha=(os.getenv('RAILWAY_GIT_COMMIT_SHA') or os.getenv('RADAR_DEPLOY_REV') or '').strip()
    return {'status':'OBSERVED' if sha else 'NOT_VERIFIED','deployed_sha':sha or None,
            'service_id':(os.getenv('RAILWAY_SERVICE_ID') or '').strip() or None,
            'environment':(os.getenv('RAILWAY_ENVIRONMENT_NAME') or '').strip() or None,
            'source':'RAILWAY_GIT_COMMIT_SHA' if os.getenv('RAILWAY_GIT_COMMIT_SHA') else ('RADAR_DEPLOY_REV' if os.getenv('RADAR_DEPLOY_REV') else None),
            'setup_allowed':False,'can_trade':False,'real_trading':False}

def latency_metrics():
    all_values=[]
    for vals in _LATENCY.values():all_values.extend(vals)
    hot=[v for vals in _LATENCY.values() for v in vals if v<=5000]
    cold=list(all_values)
    return {'hot_p95_ms':_p95(hot),'cold_p95_ms':_p95(cold),'profiled_stages':['http_v7','matrix_v7'],
            'stage_budgets_ms':{'http_v7':1000,'matrix_v7':25000},'regression_pct':None,
            'samples':len(all_values),'real_trading':False}

def _source_inputs():
    """Expensive: call only from the background prewarmer."""
    evidence,hardening,runtime,health=base6._inputs()
    proof=base6.production_proof_cached();prior=base6.tasks_151_200_cached()
    token=content_hash({'evidence':evidence.get('snapshot_hash'),'hardening':hardening.get('snapshot_hash'),
                        'health':health.get('last_success_epoch'),'learning':(health.get('learning_sync') or {}).get('last_success_epoch'),
                        'proof':proof.get('protected_digest'),'proof_status':proof.get('status'),'deploy':deployment_identity().get('deployed_sha')})
    return evidence,hardening,runtime,health,proof,prior,token

def _matrix_from_inputs(evidence,hardening,runtime,health,proof,prior):
    identity=deployment_identity();expected=proof.get('audited_commit_sha') if proof.get('verified') is True else None
    deployment={'deployed_sha':identity.get('deployed_sha'),'expected_sha':expected}
    out=build_matrix_201_270(evidence=evidence,hardening=hardening,runtime=runtime,supabase_health=health,proof=proof,
                             cache_telemetry=_CACHE.telemetry(),prior_task_groups=[prior],endpoint_metrics=latency_metrics(),deployment=deployment)
    out['source_ready']=True;out['source_mode']='BACKGROUND_PREWARMED';out['real_trading']=False
    return out

def _warming_matrix():
    tasks={str(i):{'task':i,'state':'NOT_VERIFIED','detail':'background evidence snapshot is warming','critical':i in {201,202,205,216,220,221,223,230,235,237,238,239,240,249,258,259,260,261,262,269,270}} for i in range(201,271)}
    return {'status':'WARMING_FAIL_CLOSED','tasks':tasks,'groups':{},'critical_failed':[],
            'critical_pending':[k for k,v in tasks.items() if v.get('critical')],
            'master_gate':{'status':'BLOCKED_PRE160','manual_review_only':True,'setup_allowed':False,'automatic_release':False,
                           'live_execution_allowed':False,'can_trade':False,'real_trading':False},
            'source_ready':False,'source_mode':'BACKGROUND_WARMING','stable_windows_version':'1.5.28','candidate_version':'1.6.0',
            'setup_allowed':False,'setup_built':False,'automatic_release':False,'automatic_promotion':False,
            'automatic_demotion':False,'live_execution_allowed':False,'can_trade':False,'real_trading':False}

def tasks_201_270_cached(force=False):
    if force:_CACHE.invalidate('201-270')
    value=_CACHE.peek('201-270')
    return dict(value) if isinstance(value,dict) else _warming_matrix()

def block(start,end):
    matrix=tasks_201_270_cached();tasks=matrix.get('tasks') or {}
    return {'status':f'PRE160_TASKS_{start}_{end}' if matrix.get('source_ready') else 'WARMING_FAIL_CLOSED',
            'source_ready':matrix.get('source_ready') is True,'source_mode':matrix.get('source_mode'),
            'tasks':{str(i):tasks.get(str(i)) for i in range(start,end+1)},
            'setup_allowed':False,'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,
            'can_trade':False,'real_trading':False}

def _prewarm_loop():
    """All expensive dependency reads occur here, never on an HTTP request thread."""
    while True:
        try:
            evidence,hardening,runtime,health,proof,prior,token=_source_inputs()
            captured=(evidence,hardening,runtime,health,proof,prior)
            _CACHE.prewarm('201-270',token,lambda c=captured:_matrix_from_inputs(*c))
        except Exception as exc:
            print('[pre160-v7-cache] prewarm error '+repr(exc),flush=True)
        time.sleep(30)

def _ensure_prewarm():
    global _PREWARM_STARTED
    with _PREWARM_LOCK:
        if _PREWARM_STARTED:return
        _PREWARM_STARTED=True;threading.Thread(target=_prewarm_loop,name='pre160-v7-prewarm',daemon=True).start()

class ValidationV7Handler(base6.ValidationV6Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0];started=time.monotonic()
        try:
            if path=='/pre160-audit-201-270-v1':self._send(200,tasks_201_270_cached());return
            if path=='/pre160-resilience-v7':self._send(200,block(201,220));return
            if path=='/pre160-data-authority-v7':self._send(200,block(221,240));return
            if path=='/pre160-statistical-validity-v7':self._send(200,block(241,260));return
            if path=='/pre160-autonomy-v7':self._send(200,block(261,270));return
            if path=='/pre160-master-gate-v3':
                x=tasks_201_270_cached().get('master_gate') or {};x=dict(x);x['source_ready']=tasks_201_270_cached().get('source_ready') is True;x['real_trading']=False;self._send(200,x);return
            if path=='/pre160-cache-v7':self._send(200,_CACHE.telemetry());return
            if path=='/pre160-deployment-v7':self._send(200,deployment_identity());return
        except Exception as exc:
            self._send(500,{'status':'FAILED','error':str(exc)[:800],'source_ready':False,'setup_allowed':False,'automatic_release':False,
                            'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False});return
        finally:
            if path.startswith('/pre160-'):_LATENCY[path].append(round((time.monotonic()-started)*1000,2))
        super().do_GET()

def start_runtime():
    runtime=base6.start_runtime();runtime.run_worker._Handler=ValidationV7Handler;_ensure_prewarm();return runtime

if __name__=='__main__':
    runtime=start_runtime();runtime.run_worker.main()
