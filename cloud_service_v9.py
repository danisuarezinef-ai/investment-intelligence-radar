"""Production entrypoint v9: Cloud v8 plus forward brain-evidence observability.

V9 does not alter investment execution. It reads the immutable forward ledger,
computes tasks 311-370, persists content-addressed evidence snapshots, serves
read-only readiness endpoints, supervises the existing autonomous PAPER daemon,
and exposes priorities 16-60 without starting a duplicate simulator loop.
"""
from __future__ import annotations

import threading
import time

import cloud_service_v8 as base8
from radar_forward_evidence_v2 import canonical_forward_rows, forward_evidence_snapshot
from radar_brain_calibration_v2 import brain_analytics_snapshot
from radar_brain_competition_v3 import competition_snapshot
from radar_brain_readiness_v1 import build_tasks_311_370
import radar_brain_persistence_v1 as brain_persistence
import radar_autonomous_paper_control_v1 as autonomous_paper
import radar_autonomous_learning_16_40_v1 as learning1640
import radar_autonomous_learning_41_60_v1 as learning4160
from radar_pre160_production_proof_v1 import protected_digest

REAL_TRADING=False
_LOCK=threading.RLock()
_STATE={'ready':False,'building':False,'rows':[],'evidence':None,'analytics':None,'competition':None,
       'readiness':None,'autonomous_learning':None,'autonomous_learning_41_60':None,
       'last_epoch':None,'last_error':None,'source_max_evaluated_at':None,
       'persistence':brain_persistence.telemetry()}
_STARTED=False
_START_LOCK=threading.Lock()


def _warming_tasks():
    tasks={str(i):{'task':i,'state':'NOT_VERIFIED','detail':'brain evidence snapshot is warming; fail-closed','critical':i in {311,312,314,315,316,317,319,320,321,322,323,324,326,327,328,329,330,331,332,334,336,337,341,347,349,350,355,356,361,367,369,370}} for i in range(311,371)}
    return {'status':'WARMING_FAIL_CLOSED','source_ready':False,'deep_ready':False,'tasks':tasks,
            'technical_gate':{'status':'BLOCKED_TECHNICAL','manual_review_only':True},
            'brain_readiness_gate':{'status':'NOT_READY','manual_review_only':True},
            'stable_windows_version':'1.5.28','setup_allowed':False,'setup_built':False,
            'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,
            'can_trade':False,'real_trading':False}


def _historical_metrics():
    return {}


def _technical_snapshot():
    proof=base8._cached_aux('proof','NOT_VERIFIED')
    return {
        'operational_health':base8.operational_health_v8(),
        'worker_utilization':base8.worker_utilization_v8(),
        'queue':base8.queue_telemetry_v8(),
        'provider':base8.provider_resilience_v8(),
        'partition':base8.partitioned_sync.partition_telemetry(),
        'deep_151_200':base8.tasks_151_200_cached(),
        'deep_201_270':base8.base7.tasks_201_270_cached(),
        'proof':proof,
        'protected_digest':protected_digest('.'),
        'real_trading':False,
    }


def _build_once(persist=True):
    with _LOCK:
        if _STATE['building']:return False
        _STATE['building']=True
    try:
        rows=canonical_forward_rows();evidence=forward_evidence_snapshot();analytics=brain_analytics_snapshot(rows)
        competition=competition_snapshot(rows,_historical_metrics())
        source=max((str(r.get('evaluated_at')) for r in rows if r.get('evaluated_at')),default=None)
        ptele=brain_persistence.telemetry()
        readiness=build_tasks_311_370(technical=_technical_snapshot(),evidence=evidence,analytics=analytics,
                                      competition=competition,rows=rows,persistence=ptele,external={})
        autonomous_learning=learning1640.build_priorities_16_40(rows,analytics,competition,persist=persist)
        autonomous_learning_41_60=learning4160.build_priorities_41_60(
            rows,analytics,competition,autonomous_learning,persist=persist)
        if persist and brain_persistence.enabled():
            try:
                brain_persistence.put_snapshot('reliability_v2',analytics.get('calibration') or {},source_max_evaluated_at=source)
                brain_persistence.put_snapshot('brain_analytics_v2',analytics,source_max_evaluated_at=source)
                brain_persistence.put_snapshot('brain_readiness_v1',readiness,source_max_evaluated_at=source)
                brain_persistence.stats()
            except Exception as exc:
                print('[brain-evidence-persistence] '+repr(exc),flush=True)
            ptele=brain_persistence.telemetry()
            readiness=build_tasks_311_370(technical=_technical_snapshot(),evidence=evidence,analytics=analytics,
                                          competition=competition,rows=rows,persistence=ptele,external={})
        with _LOCK:
            _STATE.update({'ready':True,'rows':rows,'evidence':evidence,'analytics':analytics,'competition':competition,
                           'readiness':readiness,'autonomous_learning':autonomous_learning,
                           'autonomous_learning_41_60':autonomous_learning_41_60,
                           'last_epoch':time.time(),'last_error':None,'source_max_evaluated_at':source,'persistence':ptele})
        return True
    except Exception as exc:
        with _LOCK:_STATE['last_error']=f'{type(exc).__name__}: {str(exc)[:800]}';_STATE['last_epoch']=time.time()
        print('[pre160-v9-brain] '+repr(exc),flush=True)
        return False
    finally:
        with _LOCK:_STATE['building']=False


def _loop():
    time.sleep(8)
    while True:
        _build_once(persist=True)
        time.sleep(300)


def _ensure_worker():
    global _STARTED
    with _START_LOCK:
        if _STARTED:return
        _STARTED=True
        threading.Thread(target=_loop,name='pre160-v9-brain-evidence',daemon=True).start()


def brain_status():
    with _LOCK:
        return {'ready':_STATE['ready'],'building':_STATE['building'],'last_epoch':_STATE['last_epoch'],
                'last_error':_STATE['last_error'],'source_max_evaluated_at':_STATE['source_max_evaluated_at'],
                'rows':len(_STATE['rows']),'persistence':dict(_STATE['persistence']),
                'autonomous_learning_ready':isinstance(_STATE.get('autonomous_learning'),dict),
                'autonomous_learning_41_60_ready':isinstance(_STATE.get('autonomous_learning_41_60'),dict),
                'setup_allowed':False,'can_trade':False,'real_trading':False}


def _get(name,warming_status='WARMING_FAIL_CLOSED'):
    with _LOCK:value=_STATE.get(name);ready=_STATE['ready']
    if ready and isinstance(value,dict):
        out=dict(value);out['source_ready']=True;out['deep_ready']=True;out['real_trading']=False;return out
    return {'status':warming_status,'source_ready':False,'deep_ready':False,'setup_allowed':False,
            'automatic_release':False,'automatic_promotion':False,'can_trade':False,'real_trading':False}


def brain_readiness():
    with _LOCK:value=_STATE.get('readiness');ready=_STATE['ready']
    if ready and isinstance(value,dict):
        out=dict(value);out['source_ready']=True;out['deep_ready']=True;out['real_trading']=False;return out
    return _warming_tasks()


def autonomous_learning():
    return _get('autonomous_learning')


def autonomous_learning_41_60():
    return _get('autonomous_learning_41_60')


def autonomous_learning_16_60():
    a=autonomous_learning();b=autonomous_learning_41_60()
    if a.get('source_ready') is not True or b.get('source_ready') is not True:
        return {'status':'WARMING_FAIL_CLOSED','source_ready':False,'deep_ready':False,
                'automatic_promotion':False,'automatic_release':False,'live_execution_allowed':False,
                'setup_allowed':False,'can_trade':False,'real_trading':False}
    return {'status':'AUTONOMOUS_PAPER_LEARNING_16_60','source_ready':True,'deep_ready':True,
            'priorities_16_40':a,'priorities_41_60':b,'dashboard_v3':b.get('dashboard_v3') or {},
            'automatic_promotion':False,'automatic_release':False,'live_execution_allowed':False,
            'setup_allowed':False,'can_trade':False,'real_trading':False}


def simulator_gate():
    return autonomous_paper.simulator_gate(technical=base8.operational_health_v8(),brain=brain_readiness())


def simulator_dashboard():
    out=autonomous_paper.dashboard(technical=base8.operational_health_v8(),brain=brain_readiness())
    learn=autonomous_learning();advanced=autonomous_learning_41_60()
    out['learning_16_40']=learn;out['learning_41_60']=advanced
    if isinstance(learn,dict) and isinstance(learn.get('balance_indicator'),dict):out['balance_indicator']=learn['balance_indicator']
    out['advanced_learning_summary']=advanced.get('dashboard_v3') if isinstance(advanced,dict) else None
    out['dashboard_contract']='AUTONOMOUS_SIMULATOR_V3';out['real_trading']=False
    out['automatic_promotion']=False;out['automatic_release']=False;out['live_execution_allowed']=False
    return out


class ValidationV9Handler(base8.ValidationV8Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        try:
            if path=='/pre160-brain-status-v1':self._send(200,brain_status());return
            if path=='/pre160-forward-evidence-v2':self._send(200,_get('evidence'));return
            if path=='/pre160-calibration-v2':self._send(200,_get('analytics'));return
            if path=='/pre160-brain-competition-v3':self._send(200,_get('competition'));return
            if path=='/pre160-brain-persistence-v1':
                out=brain_persistence.telemetry();out.update({'setup_allowed':False,'can_trade':False,'real_trading':False});self._send(200,out);return
            if path in ('/pre160-brain-readiness-v1','/pre160-audit-311-370-v1'):
                self._send(200,brain_readiness());return
            if path=='/pre160-brain-gate-v1':self._send(200,brain_readiness().get('brain_readiness_gate') or {'status':'NOT_READY','real_trading':False});return
            if path=='/autonomous-simulator/gate-v1':self._send(200,simulator_gate());return
            if path=='/autonomous-simulator/dashboard-v1':self._send(200,simulator_dashboard());return
            if path=='/autonomous-simulator/learning-v2':self._send(200,autonomous_learning());return
            if path=='/autonomous-simulator/learning-41-60-v1':self._send(200,autonomous_learning_41_60());return
            if path=='/autonomous-simulator/learning-v3':self._send(200,autonomous_learning_16_60());return
            if path=='/autonomous-simulator/watchdog-v1':self._send(200,autonomous_paper.watchdog_status());return
            if path=='/autonomous-simulator/milestones-v1':self._send(200,autonomous_paper.milestones());return
            if path=='/autonomous-simulator/control-v1':self._send(200,autonomous_paper.control_status());return
            if path=='/autonomous-simulator/learning-agenda-v1':self._send(200,autonomous_paper.learning_agenda(brain_readiness()));return
        except Exception as exc:
            self._send(500,{'status':'FAILED','error':str(exc)[:800],'setup_allowed':False,'automatic_release':False,
                            'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False});return
        super().do_GET()


def start_runtime():
    runtime=base8.start_runtime();runtime.run_worker._Handler=ValidationV9Handler
    _ensure_worker();autonomous_paper.ensure_started()
    return runtime


if __name__=='__main__':
    runtime=start_runtime();runtime.run_worker.main()
