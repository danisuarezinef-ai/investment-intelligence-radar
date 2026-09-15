"""Race-safe durable reconciliation for PAPER runtime v12.

Verifies the exact snapshots that were persisted, rather than recapturing mutable
SQLite state after the remote write. Safety remains fail-closed and REAL_TRADING
remains permanently false.
"""
from __future__ import annotations
import time
import cloud_service_v12 as v12

REAL_TRADING=False


def _identity_from_snapshots(checkpoint, core_state, session_id):
    tables=checkpoint.get('tables') or {}
    marks=tables.get('champion_paper_marks') or []
    mark=marks[-1] if marks else {}
    return {
        'state_hash':checkpoint.get('state_hash'),
        'session_id':session_id,
        'cycle':core_state.get('completed_cycles'),
        'cash':v12._money_identity(mark.get('cash')),
        'equity':v12._money_identity(mark.get('total')),
        'positions_hash':v12._positions_hash(tables.get('paper_agent_positions'),tables.get('champion_paper_positions')),
        'learning_hash':v12._canon_hash(v12._learning_view(core_state)),
        'observed_at':checkpoint.get('observed_at'),
        'backfilled':False,
        'real_trading':False,
    }


def _remote_identity(evidence):
    rcp=(evidence.get('checkpoint') or {}) if evidence.get('ok') else {}
    ra=(evidence.get('autonomy') or {}) if evidence.get('ok') else {}
    remote_core=ra.get('payload') if isinstance(ra.get('payload'),dict) else {}
    rlease=(evidence.get('lease') or {}) if evidence.get('ok') else {}
    return {
        'state_hash':rcp.get('state_hash'),
        'session_id':rlease.get('session_id'),
        'cycle':remote_core.get('completed_cycles'),
        'cash':v12._money_identity(rcp.get('champion_cash')),
        'equity':v12._money_identity(rcp.get('champion_total')),
        'positions_hash':v12._positions_hash(rcp.get('paper_positions'),rcp.get('champion_positions')) if rcp else None,
        'learning_hash':v12._canon_hash(v12._learning_view(remote_core)) if remote_core else None,
        'observed_at':rcp.get('observed_at'),
        'backfilled':False,
        'real_trading':False,
    }


def durable_sync_once(max_verify_attempts=4):
    """Persist one immutable financial/core generation and verify that generation."""
    lease=v12._lease_local()
    if lease.get('held') is not True:
        v12._DURABLE_SYNC={'status':'BLOCKED_LEASE','real_trading':False}
        return dict(v12._DURABLE_SYNC)

    core_state=v12.autonomy_core.local_state(v12.base9.autonomous_paper.simulator)
    if v12._ready():v12._TARGET_ENABLED=bool(core_state.get('enabled'))
    core=v12.autonomy_core._post({'action':'put','node_id':v12.autonomy_core.NODE_ID,'state':core_state,'real_trading':False})

    checkpoint_snapshot=v12.paper_persistence.engine_checkpoint()
    checkpoint=v12.paper_persistence._post({'action':'persist_engine_checkpoint','node_id':v12.paper_persistence.NODE_ID,
                                            'checkpoint':checkpoint_snapshot,'real_trading':False})
    checkpoint['local_state_hash']=checkpoint_snapshot.get('state_hash')
    checkpoint_ok=checkpoint.get('ok') is True or checkpoint.get('status') in {'PERSISTED_EXACT_PAPER_ENGINE','UPSERTED','OK','SYNCED'}

    admission=v12.base11.admission_status();session=admission.get('session_id')
    local=_identity_from_snapshots(checkpoint_snapshot,core_state,session)
    rec={'status':'NOT_VERIFIED','real_trading':False};remote={};evidence={};attempt=0
    for attempt in range(1,max(1,int(max_verify_attempts))+1):
        evidence=v12.remote_evidence.summary();remote=_remote_identity(evidence)
        complete=all(local.get(k) is not None and remote.get(k) is not None for k in ('state_hash','session_id','cycle','cash','equity','positions_hash','learning_hash','observed_at'))
        rec=v12.tasks2130.hard.persistence_reconciliation_gate(local,remote) if complete else {'status':'NOT_VERIFIED','real_trading':False}
        if evidence.get('ok') is True and rec.get('status')=='RECONCILED':break
        if attempt<max_verify_attempts:time.sleep(min(3.0,float(attempt)))

    ok=core.get('ok') is True and checkpoint_ok and evidence.get('ok') is True and rec.get('status')=='RECONCILED'
    v12._DURABLE_SYNC={'status':'RECONCILED' if ok else 'DEGRADED','autonomy_core':core.get('status'),'checkpoint':checkpoint.get('status'),
                       'checkpoint_ok':checkpoint_ok,'checkpoint_hash':checkpoint_snapshot.get('state_hash'),'reconciliation':rec,
                       'local_identity':local,'remote_identity':remote,'verify_attempts':attempt,'snapshot_consistent':True,'real_trading':False}
    if ok:print('[paper-v12] durable reconciliation RECONCILED cycle={} hash={} snapshot=consistent'.format(local.get('cycle'),str(local.get('state_hash') or '')[:12]),flush=True)
    else:print('[paper-v12] durable reconciliation DEGRADED blockers={} mismatches={} snapshot=consistent'.format(rec.get('blockers'),rec.get('mismatched_fields')),flush=True)
    return dict(v12._DURABLE_SYNC)


def install():
    v12._durable_sync_once=durable_sync_once
    return {'status':'INSTALLED','owner':'cloud_service_v12._durable_sync_once','snapshot_consistent':True,'real_trading':False}
