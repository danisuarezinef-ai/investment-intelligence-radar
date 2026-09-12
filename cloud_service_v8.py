"""Production entrypoint v8: v7 plus runtime closure for tasks 271-310.

Changes are transport/audit only:
- generic Supabase sync is partitioned into bounded idempotent families;
- tasks 151-200 are served from a light fail-closed surface until the shared deep worker
  populates exact cached evidence;
- /supabase-health-v1 reports the actual partitioned generic transport plus learning sync.

Windows remains 1.5.28 and REAL_TRADING=false.
"""
from __future__ import annotations

import threading

import cloud_service as base_cloud
import cloud_service_v7 as base7
import radar_supabase_sync_partitioned_v2 as partitioned_sync

REAL_TRADING = False
_DEEP_151_LOCK = threading.RLock()
_DEEP_151 = {'matrix': None, 'manifest': None, 'release': None, 'proof': None}
_ORIGINAL_DEEP = base7._collect_deep


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


def supabase_health_v8():
    generic=partitioned_sync.sync_telemetry();learning=base7.learning_sync.learning_sync_telemetry()
    if generic.get('status')=='HEALTHY' and learning.get('status')=='HEALTHY':status='HEALTHY'
    elif generic.get('status') in ('STARTING','NOT_CONFIGURED') or learning.get('status') in ('STARTING','NOT_CONFIGURED'):status='STARTING'
    else:status='DEGRADED'
    return {'status':status,'generic_sync':generic,'learning_sync':learning,
            'queue':base7.remote_queue.probe_telemetry(),'provider_transport':base7._PROVIDER.telemetry(),
            'setup_allowed':False,'automatic_release':False,'can_trade':False,'real_trading':False}


def tasks_271_310_v8():
    r=base7.readiness_snapshot();queue=base7.remote_queue.probe_telemetry();queue.update(base7.remote_queue.queue_contract())
    proof=base7.verify_proof_v3();proof['contract']=base7.proof_v3_contract();old=base7.tasks_201_270_cached().get('master_gate') or {}
    dep=base7.deployment_identity();proof_sha=proof.get('audited_commit_sha') if proof.get('verified') else None
    return base7.build_matrix_271_310(readiness=r,queue=queue,provider=base7._PROVIDER.telemetry(),
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
            if path=='/pre160-audit-271-310-v1':self._send(200,tasks_271_310_v8());return
            if path=='/pre160-master-gate-v4':self._send(200,tasks_271_310_v8().get('master_gate_v4') or {});return
        except Exception as exc:
            self._send(500,{'status':'FAILED','error':str(exc)[:800],'setup_allowed':False,'automatic_release':False,
                            'automatic_promotion':False,'automatic_demotion':False,'can_trade':False,'real_trading':False});return
        super().do_GET()


def start_runtime():
    # cloud_service.supabase_sync_loop resolves this global at call time; patch before
    # base runtime creates worker threads.
    base_cloud.sync_once=partitioned_sync.sync_once
    base7._collect_deep=_collect_deep_v8
    runtime=base7.start_runtime();runtime.run_worker._Handler=ValidationV8Handler
    return runtime


if __name__=='__main__':
    runtime=start_runtime();runtime.run_worker.main()
