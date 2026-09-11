"""Production entrypoint v4: unified v3 authority/runtime plus closed-loop PAPER layer.

v4 composes over cloud_service_v3 so Railway actually serves the pre-1.6 endpoints,
restores durable PAPER/autonomy authority, and runs the autonomous simulator. The
extra closed-loop cycle remains PAPER-only and never creates a second HTTP server.
"""
import json
import threading
import time

import cloud_service_v3 as base3
from radar_core import now
from radar_forward_engine import mature_forward_outcomes
from radar_closed_loop_runtime_v1 import closed_loop_cycle
from radar_pre160_cloud_v2 import runtime_snapshot,readiness_snapshot,mobile_runtime_summary

REAL_TRADING=False
_V4_RUNTIME_STARTED=False
_PRE160_V2_CACHE={'at':0.0,'runtime':None,'readiness':None,'mobile':None}
_PRE160_V2_CACHE_SECONDS=60.0


def pre160_runtime_cached(force=False):
    current=time.monotonic();cached=_PRE160_V2_CACHE.get('runtime')
    if not force and cached is not None and current-float(_PRE160_V2_CACHE.get('at') or 0)<_PRE160_V2_CACHE_SECONDS:return dict(cached)
    try:
        runtime=runtime_snapshot();readiness=readiness_snapshot(runtime);mobile=mobile_runtime_summary(runtime)
        for payload in (runtime,readiness,mobile):payload['cache_seconds']=int(_PRE160_V2_CACHE_SECONDS);payload['real_trading']=False
        _PRE160_V2_CACHE.update({'at':current,'runtime':dict(runtime),'readiness':dict(readiness),'mobile':dict(mobile)})
        return runtime
    except Exception as exc:
        if cached is not None:
            payload=dict(cached);payload['status']='STALE_CACHE';payload['error']=str(exc)[:700];payload['real_trading']=False;return payload
        return {'status':'DEGRADED','scorecards':[],'error':str(exc)[:700],'setup_allowed':False,'can_trade':False,'real_trading':False}


def pre160_readiness_cached():
    pre160_runtime_cached();payload=_PRE160_V2_CACHE.get('readiness')
    return dict(payload) if payload is not None else {'status':'DEGRADED','setup_allowed':False,'can_trade':False,'real_trading':False}


def mobile_summary_cached():
    pre160_runtime_cached();payload=_PRE160_V2_CACHE.get('mobile')
    return dict(payload) if payload is not None else {'status':'DEGRADED','display_mode':'PAPER','setup_allowed':False,'can_trade':False,'real_trading':False}


class ValidationV4Handler(base3.ValidationV3Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        try:
            if path=='/pre160-runtime-v2':self._send(200,pre160_runtime_cached());return
            if path=='/pre160-readiness-v1':self._send(200,pre160_readiness_cached());return
            if path=='/mobile-summary-v2':self._send(200,mobile_summary_cached());return
            if path=='/opportunities-369-v1':
                payload=pre160_runtime_cached().get('opportunities_369') or {};payload=dict(payload);payload['can_trade']=False;payload['real_trading']=False;self._send(200,payload);return
        except Exception as exc:
            self._send(500,{'status':'FAILED','error':str(exc)[:800],'setup_allowed':False,'can_trade':False,'real_trading':False});return
        super().do_GET()


def closed_loop_runtime_loop(interval_seconds=300):
    """Add the decision closed loop on top of v3's forward-sync/autonomy runtime."""
    print('[closed-loop] prospective PAPER runtime enabled; REAL_TRADING OFF',flush=True)
    time.sleep(20)
    base=base3.base_v2.base
    while True:
        try:
            matured=mature_forward_outcomes();cycle=closed_loop_cycle('1d')
            base.write_status(closed_loop='OK',closed_loop_at=now(),closed_loop_status=cycle.get('status'),
                              closed_loop_forward=cycle.get('forward_records',0),closed_loop_matured=matured,real_trading=False)
            print('[closed-loop] '+json.dumps({'matured':matured,'status':cycle.get('status'),'forward_records':cycle.get('forward_records'),
                'optimizer':(cycle.get('optimizer') or {}).get('status'),'competition':(cycle.get('champion_challenger') or {}).get('status'),
                'execution':(cycle.get('execution') or {}).get('status'),'real_trading':False},ensure_ascii=False)[:2600],flush=True)
        except Exception as exc:
            print('[closed-loop] ERROR '+repr(exc),flush=True);base.write_status(closed_loop='ERROR',closed_loop_error=str(exc)[:700],real_trading=False)
        time.sleep(max(60,int(interval_seconds)))


def start_v3_runtime():
    """Start all v3 workers exactly once, then return the underlying cloud base."""
    global _V4_RUNTIME_STARTED
    base=base3.base_v2.base
    # v4 owns the final HTTP handler but delegates every older route to v3.
    base.run_worker._Handler=ValidationV4Handler
    if _V4_RUNTIME_STARTED:return base
    _V4_RUNTIME_STARTED=True
    base3.init_autonomous_simulator();base3.init_e2e()
    try:
        restored=base3.rehydrate_authority();base3._AUTHORITY_STATUS={'status':'RESTORED','result':restored,'real_trading':False}
        print('[authority] restore '+json.dumps(restored,ensure_ascii=False)[:2200],flush=True)
    except Exception as exc:
        base3._AUTHORITY_STATUS={'status':'RESTORE_FAILED_FAIL_CLOSED','error':str(exc)[:700],'real_trading':False};print('[authority] RESTORE ERROR '+repr(exc),flush=True)
    try:
        engine_restored=base3.rehydrate_engine_checkpoint();base3._PAPER_ENGINE_STATUS=dict(engine_restored)
        print('[paper-engine] restore '+json.dumps(engine_restored,ensure_ascii=False)[:2200],flush=True)
    except Exception as exc:
        base3._PAPER_ENGINE_STATUS={'status':'RESTORE_FAILED_FAIL_CLOSED','error':str(exc)[:700],'real_trading':False};print('[paper-engine] RESTORE ERROR '+repr(exc),flush=True);raise
    workers=((base.supabase_sync_loop,'supabase-sync'),(base.learning_sync_loop,'learning-sync'),(base3._resilient_learning_loop,'learning-engine'),
             (base3._forward_outcome_sync_loop,'forward-outcome-sync'),(base3.autonomous_simulator_loop,'autonomous-simulator'),
             (base3.soak_loop,'autonomy-soak'),(base3._authority_sync_loop,'persistent-authority'),(closed_loop_runtime_loop,'closed-loop-paper'))
    for target,name in workers:threading.Thread(target=target,name=name,daemon=True).start()
    return base


if __name__=='__main__':
    runtime=start_v3_runtime();runtime.run_worker.main()
