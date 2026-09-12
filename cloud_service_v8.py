"""Production entrypoint v8: v7 plus runtime closure for tasks 271-310.

Transport/audit changes only:
- generic Supabase sync is partitioned into bounded idempotent families with durable backpressure;
- tasks 151-200 are served from a light fail-closed surface until the shared deep worker
  populates exact cached evidence;
- controlled non-investment probes verify DLQ/reprocess and circuit/rate-governor behavior;
- operational health is explicitly separate from investment scoring.

Windows remains 1.5.28 and REAL_TRADING=false.
"""
from __future__ import annotations

import threading
import time

import cloud_service as base_cloud
import cloud_service_v7 as base7
import radar_supabase_sync_partitioned_v2 as partitioned_sync
from radar_operational_health_v2 import operational_health, worker_utilization
from radar_provider_resilience_v2 import controlled_resilience_probe

REAL_TRADING = False
_DEEP_151_LOCK = threading.RLock()
_DEEP_151 = {'matrix': None, 'manifest': None, 'release': None, 'proof': None}
_ORIGINAL_DEEP = base7._collect_deep
_CONTROLLED_LOCK = threading.RLock()
_CONTROLLED = {
    'queue': {'status':'NOT_STARTED','real_trading':False},
    'provider': {'status':'NOT_STARTED','real_trading':False},
    'attempts': 0,
    'last_epoch': None,
}
_CONTROLLED_STARTED = False
_CONTROLLED_START_LOCK = threading.Lock()


def _lite_151_200():
    tasks={str(i):{'task':i,'state':'NOT_VERIFIED','detail':'deep 151-200 evidence not ready; served fail-closed','critical':i in {151,152,153,154,155,156,157,158,159,160,171,172,173,174,175,181,182,183,184,185,191,192,193,194,195,196,197,198,199,200}} for i in range(151,201)}
    return {'status':'LITE_READY_FAIL_CLOSED','source_ready':True,'lite_ready':True,'deep_ready':False,'tasks':tasks,
            'stable_windows_version':'1.5.28','setup_allowed':False,'automatic_release':False,'automatic_promotion':False,
            'automatic_demotion':False,'can_trade':False,'real_trading':False}


def _collect_deep_v8():
    result=_ORIGINAL_DEEP()
    try:
        matrix=base7.base6.tasks_151_200_cached()
        manifest=base7.base6.recovery_manifest_cached()
        release=base7.base6.release_authority_cached()
        proof=base7.base6.production_proof_cached()
        with _DEEP_151_LOCK:
            _DEEP_151.update({'matrix':dict(matrix),'manifest':dict(manifest),'release':dict(release),'proof':dict(proof)})
    except Exception as exc:
        print('[pre160-v8-151-cache] '+repr(exc),flush=True)
    return result


def tasks_151_200_cached():
    with _DEEP_151_LOCK:
        matrix=_DEEP_151.get('matrix')
        if isinstance(matrix,dict):
            out=dict(matrix);out.update({'source_ready':True,'lite_ready':True,'deep_ready':True,'real_trading':False});return out
    return _lite_151_200()


def block_151_200(start,end):
    matrix=tasks_151_200_cached();tasks=matrix.get('tasks') or {}
    return {'status':f'PRE160_TASKS_{start}_{end}' if matrix.get('deep_ready') else 'LITE_READY_FAIL_CLOSED',
            'source_ready':True,'lite_ready':True,'deep_ready':matrix.get('deep_ready') is True,
            'tasks':{str(i):tasks.get(str(i)) for i in range(start,end+1)},'setup_allowed':False,
            'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False}


def _cached_aux(name,fallback_status='LITE_READY_FAIL_CLOSED'):
    with _DEEP_151_LOCK:
        value=_DEEP_151.get(name)
        if isinstance(value,dict):
            out=dict(value);out['source_ready']=True;out['deep_ready']=True;out['real_trading']=False;return out
    return {'status':fallback_status,'source_ready':True,'deep_ready':False,'setup_allowed':False,'automatic_release':False,
            'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False}


def controlled_probe_snapshot():
    with _CONTROLLED_LOCK:
        return {'queue':dict(_CONTROLLED['queue']),'provider':dict(_CONTROLLED['provider']),
                'attempts':_CONTROLLED['attempts'],'last_epoch':_CONTROLLED['last_epoch'],'real_trading':False}


def _controlled_probe_loop():
    # A few seconds allows the service healthcheck to come up first. Failed probes are
    # retried a bounded number of times and never affect investment/PAPER state.
    time.sleep(5)
    for attempt in range(1,4):
        queue_result={'status':'NOT_VERIFIED','real_trading':False}
        provider_result={'status':'NOT_VERIFIED','real_trading':False}
        try:
            queue_result=base7.remote_queue.controlled_dlq_probe()
            base7.remote_queue.remote_stats()
        except Exception as exc:
            queue_result={'status':'FAILED','error':f'{type(exc).__name__}: {str(exc)[:500]}','real_trading':False}
        try:
            provider_result=controlled_resilience_probe()
        except Exception as exc:
            provider_result={'status':'FAILED','error':f'{type(exc).__name__}: {str(exc)[:500]}','real_trading':False}
        with _CONTROLLED_LOCK:
            _CONTROLLED.update({'queue':dict(queue_result),'provider':dict(provider_result),'attempts':attempt,'last_epoch':time.time()})
        if queue_result.get('status')=='PASS' and provider_result.get('status')=='PASS':
            print('[pre160-v8-controlled-probes] PASS',flush=True)
            return
        print('[pre160-v8-controlled-probes] retry queue={} provider={}'.format(queue_result.get('status'),provider_result.get('status')),flush=True)
        time.sleep(30)


def _ensure_controlled_probes():
    global _CONTROLLED_STARTED
    with _CONTROLLED_START_LOCK:
        if _CONTROLLED_STARTED:return
        _CONTROLLED_STARTED=True
        threading.Thread(target=_controlled_probe_loop,name='pre160-v8-controlled-probes',daemon=True).start()


def provider_resilience_v8():
    out=dict(base7._PROVIDER.telemetry())
    out['controlled_probe']=controlled_probe_snapshot().get('provider')
    out['external_failover_verified']=out.get('failover_verified') is True
    out['real_trading']=False
    return out


def queue_telemetry_v8():
    out=base7.remote_queue.probe_telemetry();out.update(base7.remote_queue.queue_contract())
    out['controlled_probe']=controlled_probe_snapshot().get('queue')
    out['real_trading']=False
    return out


def supabase_health_v8():
    generic=partitioned_sync.sync_telemetry();learning=base7.learning_sync.learning_sync_telemetry()
    if generic.get('status')=='HEALTHY' and learning.get('status')=='HEALTHY':status='HEALTHY'
    elif generic.get('status') in ('STARTING','NOT_CONFIGURED') or learning.get('status') in ('STARTING','NOT_CONFIGURED'):status='STARTING'
    else:status='DEGRADED'
    return {'status':status,'generic_sync':generic,'learning_sync':learning,
            'queue':queue_telemetry_v8(),'provider_transport':provider_resilience_v8(),
            'setup_allowed':False,'automatic_release':False,'can_trade':False,'real_trading':False}


def operational_health_v8():
    return operational_health(generic_sync=partitioned_sync.sync_telemetry(),
        learning_sync=base7.learning_sync.learning_sync_telemetry(),queue=queue_telemetry_v8(),
        provider=provider_resilience_v8(),readiness=base7.readiness_snapshot(),partition=partitioned_sync.partition_telemetry())


def worker_utilization_v8():
    return worker_utilization(generic_sync=partitioned_sync.sync_telemetry(),
        learning_sync=base7.learning_sync.learning_sync_telemetry(),partition=partitioned_sync.partition_telemetry(),
        readiness=base7.readiness_snapshot(),queue=queue_telemetry_v8(),provider=provider_resilience_v8())


def tasks_271_310_v8():
    r=base7.readiness_snapshot();queue=queue_telemetry_v8()
    proof=base7.verify_proof_v3();proof['contract']=base7.proof_v3_contract();old=base7.tasks_201_270_cached().get('master_gate') or {}
    dep=base7.deployment_identity();proof_sha=proof.get('audited_commit_sha') if proof.get('verified') else None
    return base7.build_matrix_271_310(readiness=r,queue=queue,provider=provider_resilience_v8(),
        generic_sync=partitioned_sync.sync_telemetry(),learning_sync=base7.learning_sync.learning_sync_telemetry(),
        proof_v3=proof,deployment={'expected_sha':proof_sha,'deployed_sha':dep.get('deployed_sha')},ci_evidence={},prior_gate=old)


class ValidationV8Handler(base7.ValidationV7Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        try:
            if path=='/pre160-audit-151-200-v1':self._send(200,tasks_151_200_cached());return
            if path=='/pre160-slo-v1':self._send(200,block_151_200(151,160));return
            if path=='/pre160-data-integrity-v1':self._send(200,block_151_200(161,170));return
            if path=='/pre160-evidence-maturity-v3':self._send(200,block_151_200(171,180));return
            if path=='/pre160-governance-v3':self._send(200,block_151_200(181,190));return
            if path=='/pre160-recovery-v2':self._send(200,_cached_aux('manifest'));return
            if path=='/pre160-release-authority-v2':self._send(200,_cached_aux('release','BLOCKED_PRE160'));return
            if path=='/pre160-production-proof-v1':self._send(200,_cached_aux('proof','NOT_VERIFIED'));return
            if path=='/supabase-health-v1':self._send(200,supabase_health_v8());return
            if path=='/pre160-sync-partitions-v2':self._send(200,partitioned_sync.partition_telemetry());return
            if path=='/pre160-provider-resilience-v2':self._send(200,provider_resilience_v8());return
            if path=='/pre160-queue-v3':self._send(200,queue_telemetry_v8());return
            if path=='/pre160-operational-health-v2':self._send(200,operational_health_v8());return
            if path=='/pre160-worker-utilization-v1':self._send(200,worker_utilization_v8());return
            if path=='/pre160-audit-271-310-v1':self._send(200,tasks_271_310_v8());return
            if path=='/pre160-master-gate-v4':self._send(200,tasks_271_310_v8().get('master_gate_v4') or {});return
        except Exception as exc:
            self._send(500,{'status':'FAILED','error':str(exc)[:800],'setup_allowed':False,'automatic_release':False,
                            'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False});return
        super().do_GET()


def start_runtime():
    base_cloud.sync_once=partitioned_sync.sync_once
    base7._collect_deep=_collect_deep_v8
    runtime=base7.start_runtime();runtime.run_worker._Handler=ValidationV8Handler
    _ensure_controlled_probes()
    return runtime


if __name__=='__main__':
    runtime=start_runtime();runtime.run_worker.main()
