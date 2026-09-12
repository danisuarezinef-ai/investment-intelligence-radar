"""Production entrypoint v5: v4 runtime plus post-150 reliability observability.

This layer is read-only. It does not alter PAPER decisions, promotion governance,
Windows packaging, or trading authority. REAL_TRADING remains false.
"""
from __future__ import annotations

import cloud_service_v4 as base4
from radar_supabase_sync import sync_telemetry

REAL_TRADING = False

_PENDING_SAMPLE = {
    'all_samples_mature', 'calibration_mature', 'cost_sensitivity_available',
    'regime_horizon_mature', 'stress_observed', 'anti_overfit_available',
    'provenance_complete',
}
_PENDING_TIME = {'runtime_30d'}


def _check_state(name, value, degraded=False):
    if degraded:
        return 'NOT_VERIFIED'
    if value is True:
        return 'PASS'
    if name in _PENDING_TIME:
        return 'PENDING_TIME'
    if name in _PENDING_SAMPLE:
        return 'PENDING_SAMPLE'
    if value is False:
        return 'PENDING_SAMPLE'
    return 'NOT_VERIFIED'


def readiness_board():
    evidence = base4.pre160_evidence_cached()
    hardening = base4.pre160_hardening_cached()
    audit = base4.tasks_131_150_cached()
    readiness = dict(evidence.get('readiness_1_6') or {})
    checks = dict(readiness.get('checks') or {})
    degraded = str(evidence.get('status') or '').upper() in {'DEGRADED', 'FAILED'}
    rows = [
        {'check': name, 'state': _check_state(name, value, degraded), 'observed': value}
        for name, value in checks.items()
    ]
    trace = dict(audit.get('decision_trace') or {})
    exact = int(audit.get('transactional_exact') or 0)
    task150 = 'PASS' if exact > 0 and trace.get('status') not in (None, 'EVIDENCE_PENDING') and not trace.get('blockers') else 'PENDING_SAMPLE'
    return {
        'status': readiness.get('status') or evidence.get('status') or 'NOT_VERIFIED',
        'score_pct': readiness.get('score_pct'),
        'checks': rows,
        'blockers': list(readiness.get('blockers') or []),
        'task_150': {
            'state': task150,
            'transactional_envelopes_observed': exact,
            'decision_trace_status': trace.get('status'),
            'trace_blockers': list(trace.get('blockers') or []),
            'rule': 'Natural PAPER evidence only; no force, reconstruction or backfill.',
        },
        'readiness_countdown': hardening.get('readiness_countdown'),
        'supabase': sync_telemetry(),
        'setup_allowed': False,
        'automatic_release': False,
        'automatic_promotion': False,
        'automatic_demotion': False,
        'can_trade': False,
        'real_trading': False,
    }


def decision_provenance_status():
    audit = base4.tasks_131_150_cached()
    trace = dict(audit.get('decision_trace') or {})
    source = dict(audit.get('envelope_source') or {})
    return {
        'status': trace.get('status') or 'EVIDENCE_PENDING',
        'transactional_exact': int(audit.get('transactional_exact') or 0),
        'ledger_fallback': int(audit.get('ledger_fallback') or 0),
        'strategy_versions_missing': int(audit.get('strategy_versions_missing') or 0),
        'source': source,
        'decision_trace': trace,
        'blockers': list(audit.get('blockers') or []),
        'entry_linkage': trace.get('linkage'),
        'uses_exit_fields_for_entry_linkage': bool(trace.get('uses_exit_fields_for_entry_linkage', False)),
        'natural_evidence_only': True,
        'backfill_allowed': False,
        'can_trade': False,
        'real_trading': False,
    }


class ValidationV5Handler(base4.ValidationV4Handler):
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        try:
            if path == '/supabase-health-v1':
                self._send(200, sync_telemetry())
                return
            if path == '/pre160-readiness-board-v1':
                self._send(200, readiness_board())
                return
            if path == '/decision-provenance-v1':
                self._send(200, decision_provenance_status())
                return
        except Exception as exc:
            self._send(500, {
                'status': 'FAILED',
                'error': str(exc)[:800],
                'setup_allowed': False,
                'can_trade': False,
                'real_trading': False,
            })
            return
        super().do_GET()


def start_runtime():
    runtime = base4.start_v3_runtime()
    runtime.run_worker._Handler = ValidationV5Handler
    return runtime


if __name__ == '__main__':
    runtime = start_runtime()
    runtime.run_worker.main()
