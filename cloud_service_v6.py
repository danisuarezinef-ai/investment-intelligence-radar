"""Production entrypoint v6: v5 plus tasks 151-200 audit/recovery/release authority.

Read-only governance layer. Windows remains 1.5.28 and REAL_TRADING is false.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import cloud_service_v5 as base5
from radar_learning_sync import MAX_LEARNING_BATCH
from radar_supabase_sync import MAX_SYNC_BATCH
from radar_pre160_controls_v6 import build_task_matrix
from radar_pre160_recovery_v2 import build_recovery_manifest, digest
from radar_pre160_release_authority_v2 import build_release_authority
from radar_pre160_production_proof_v1 import production_proof_status

REAL_TRADING = False
_CACHE_SECONDS = 60.0
_CACHE = {'at': 0.0, 'matrix': None, 'manifest': None, 'release': None, 'production_proof': None}


def _version():
    try:
        return str(json.loads(Path('version.json').read_text(encoding='utf-8-sig')).get('version') or 'UNKNOWN')
    except Exception:
        return 'UNKNOWN'


def _inputs():
    evidence = dict(base5.base4.pre160_evidence_cached())
    hardening = dict(base5.base4.pre160_hardening_cached())
    provenance = base5.base4.tasks_131_150_cached()
    for key in ('decision_trace', 'transactional_exact', 'ledger_fallback', 'strategy_versions_missing', 'envelope_source', 'decision_envelope_provenance', 'blockers'):
        if key in provenance:
            hardening[key] = provenance[key]
    evidence['snapshot_hash'] = digest(evidence)
    hardening['snapshot_hash'] = digest(hardening)
    runtime = base5.base4.pre160_runtime_cached()
    health = dict(base5.supabase_health())
    health['max_batch'] = int(MAX_SYNC_BATCH)
    learning = dict(health.get('learning_sync') or {})
    learning.setdefault('max_batch', int(MAX_LEARNING_BATCH))
    health['learning_sync'] = learning
    return evidence, hardening, runtime, health


def tasks_151_200_cached(force=False):
    current = time.monotonic()
    if not force and _CACHE.get('matrix') is not None and current - float(_CACHE.get('at') or 0) < _CACHE_SECONDS:
        return dict(_CACHE['matrix'])
    evidence, hardening, runtime, health = _inputs()
    proof = production_proof_status()
    matrix = build_task_matrix(
        evidence=evidence,
        hardening=hardening,
        runtime=runtime,
        supabase_health=health,
        version=_version(),
        production_proof=proof.get('verified') is True,
    )
    manifest = build_recovery_manifest(
        evidence=evidence,
        hardening=hardening,
        health=health,
        task_matrix=matrix,
        version=_version(),
    )
    release = build_release_authority(matrix, manifest, stable_version=_version(), candidate_version='1.6.0')
    matrix['external_production_proof'] = proof
    release['external_production_proof'] = proof
    for payload in (matrix, manifest, release, proof):
        payload['cache_seconds'] = int(_CACHE_SECONDS)
        payload['real_trading'] = False
    _CACHE.update({'at': current, 'matrix': dict(matrix), 'manifest': dict(manifest), 'release': dict(release), 'production_proof': dict(proof)})
    return matrix


def recovery_manifest_cached():
    tasks_151_200_cached()
    return dict(_CACHE.get('manifest') or {'status': 'NOT_VERIFIED', 'real_trading': False})


def release_authority_cached():
    tasks_151_200_cached()
    return dict(_CACHE.get('release') or {'status': 'BLOCKED_PRE160', 'setup_allowed': False, 'real_trading': False})


def production_proof_cached():
    tasks_151_200_cached()
    return dict(_CACHE.get('production_proof') or {'status': 'NOT_VERIFIED', 'verified': False, 'real_trading': False})


def task_block(start, end):
    matrix = tasks_151_200_cached()
    tasks = matrix.get('tasks') or {}
    subset = {str(i): tasks.get(str(i)) for i in range(int(start), int(end) + 1)}
    return {
        'status': f'PRE160_TASKS_{start}_{end}',
        'tasks': subset,
        'setup_allowed': False,
        'automatic_release': False,
        'automatic_promotion': False,
        'automatic_demotion': False,
        'can_trade': False,
        'real_trading': False,
    }


class ValidationV6Handler(base5.ValidationV5Handler):
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        try:
            if path == '/pre160-audit-151-200-v1':
                self._send(200, tasks_151_200_cached())
                return
            if path == '/pre160-slo-v1':
                self._send(200, task_block(151, 160))
                return
            if path == '/pre160-data-integrity-v1':
                self._send(200, task_block(161, 170))
                return
            if path == '/pre160-evidence-maturity-v3':
                self._send(200, task_block(171, 180))
                return
            if path == '/pre160-governance-v3':
                self._send(200, task_block(181, 190))
                return
            if path == '/pre160-recovery-v2':
                self._send(200, recovery_manifest_cached())
                return
            if path == '/pre160-release-authority-v2':
                self._send(200, release_authority_cached())
                return
            if path == '/pre160-production-proof-v1':
                self._send(200, production_proof_cached())
                return
        except Exception as exc:
            self._send(500, {
                'status': 'FAILED',
                'error': str(exc)[:800],
                'setup_allowed': False,
                'automatic_release': False,
                'automatic_promotion': False,
                'automatic_demotion': False,
                'can_trade': False,
                'real_trading': False,
            })
            return
        super().do_GET()


def start_runtime():
    runtime = base5.start_runtime()
    runtime.run_worker._Handler = ValidationV6Handler
    return runtime


if __name__ == '__main__':
    runtime = start_runtime()
    runtime.run_worker.main()
