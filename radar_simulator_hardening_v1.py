"""Fail-closed hardening contracts for the autonomous PAPER simulator.

This module does not place orders, promote models, release builds, or enable live
trading.  It turns the first seven simulator-hardening priorities into explicit,
testable gates that can be composed with the existing production control plane.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from radar_paper_execution_v2 import simulate_fill

REAL_TRADING = False


def _utc(value: Any):
    if value in (None, ''):
        return None
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None
    if d.tzinfo is None:
        return None
    return d.astimezone(timezone.utc)


def _age_seconds(value: Any, now: Any = None):
    d = _utc(value)
    n = _utc(now) if now is not None else datetime.now(timezone.utc)
    if d is None or n is None:
        return None
    return max(0.0, (n - d).total_seconds())


def exact_restore_gate(restore: dict[str, Any] | None):
    r = restore or {}
    checks = {
        'exact_status': r.get('status') == 'RESTORED_EXACT_PAPER_ENGINE',
        'verified': r.get('verified') is True,
        'hash_equal': bool(r.get('remote_state_hash')) and r.get('remote_state_hash') == r.get('local_state_hash'),
        'no_backfill': r.get('backfill_used') is False,
        'no_reconstruction': r.get('reconstructed') is False,
        'cannot_trade': r.get('can_trade') is False,
        'real_trading_frozen': r.get('real_trading') is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {'status': 'PASS' if not blockers else 'FAIL', 'checks': checks, 'blockers': blockers,
            'real_trading': False}


def continuity_gate(*, session: dict[str, Any] | None, simulator: dict[str, Any] | None,
                    control: dict[str, Any] | None = None, lease: dict[str, Any] | None = None,
                    now: Any = None, max_cycle_age_seconds: int = 3600,
                    max_heartbeat_age_seconds: int = 900):
    s = session or {}; sim = simulator or {}; ctl = control or {}; l = lease or {}
    cycle_age = _age_seconds(sim.get('last_cycle_at'), now)
    heartbeat_age = _age_seconds(l.get('heartbeat_at') or ctl.get('heartbeat_at') or ctl.get('last_supervisor_at'), now)
    checks = {
        'session_id_present': bool(s.get('session_id')),
        'simulator_active': sim.get('active') is True,
        'cycle_fresh': cycle_age is not None and cycle_age <= max_cycle_age_seconds,
        'no_runtime_error': not bool(sim.get('last_error')),
        'single_instance_proven': int(l.get('active_instances', 0) or 0) == 1,
        'lease_owner_present': bool(l.get('owner_id')),
        'heartbeat_fresh': heartbeat_age is not None and heartbeat_age <= max_heartbeat_age_seconds,
        'duplicate_simulator_blocked': ctl.get('duplicate_simulator_started') is False,
        'real_trading_frozen': sim.get('real_trading') is False and s.get('real_trading') is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {'status': 'PASS' if not blockers else 'FAIL', 'checks': checks, 'blockers': blockers,
            'cycle_age_seconds': cycle_age, 'heartbeat_age_seconds': heartbeat_age,
            'real_trading': False}


def market_snapshot_gate(snapshot: dict[str, Any] | None, *, now: Any = None,
                         max_age_seconds: int = 180):
    m = snapshot or {}; age = _age_seconds(m.get('observed_at'), now)
    missing_kind = str(m.get('missing_kind') or '').upper()
    checks = {
        'symbol_present': bool(str(m.get('symbol') or '').strip()),
        'source_present': bool(str(m.get('source') or '').strip()),
        'timestamp_utc_aware': _utc(m.get('observed_at')) is not None,
        'fresh': age is not None and age <= max_age_seconds,
        'mid_price_valid': isinstance(m.get('mid_price'), (int, float)) and float(m.get('mid_price')) > 0,
        'volume_valid': isinstance(m.get('available_volume'), (int, float)) and float(m.get('available_volume')) >= 0,
        'market_open_known': isinstance(m.get('market_open'), bool),
        'provider_not_failed': missing_kind not in {'PROVIDER_FAILURE', 'STALE', 'DELAYED'},
        'point_in_time_hash_present': bool(m.get('snapshot_hash')),
    }
    blockers = [k for k, v in checks.items() if not v]
    return {'status': 'PASS' if not blockers else 'FAIL', 'checks': checks, 'blockers': blockers,
            'age_seconds': age, 'real_trading': False}


def safe_paper_fill(order: dict[str, Any] | None, market: dict[str, Any] | None, *,
                    now: Any = None, assumptions: dict[str, Any] | None = None,
                    max_age_seconds: int = 180):
    gate = market_snapshot_gate(market, now=now, max_age_seconds=max_age_seconds)
    if gate['status'] != 'PASS':
        return {'status': 'REJECTED', 'reason': 'market_evidence_gate_failed', 'market_gate': gate,
                'filled_quantity': 0.0, 'broker_connected': False, 'can_submit_order': False,
                'real_trading': False}
    if market.get('market_open') is not True:
        return {'status': 'REJECTED', 'reason': 'market_closed', 'market_gate': gate,
                'filled_quantity': 0.0, 'broker_connected': False, 'can_submit_order': False,
                'real_trading': False}
    out = simulate_fill(order, market, assumptions)
    out['market_gate'] = gate
    out['market_snapshot_hash'] = market.get('snapshot_hash')
    out['decision_market_observed_at'] = market.get('observed_at')
    out['real_trading'] = False
    out['can_submit_order'] = False
    out['broker_connected'] = False
    return out


def temporal_isolation_gate(decision: dict[str, Any] | None):
    d = decision or {}; decision_at = _utc(d.get('decision_at'))
    known = list(d.get('evidence') or [])
    future = []
    invalid = []
    for i, item in enumerate(known):
        if not isinstance(item, dict):
            invalid.append(i); continue
        known_at = _utc(item.get('known_at') or item.get('observed_at'))
        if known_at is None or decision_at is None:
            invalid.append(i)
        elif known_at > decision_at:
            future.append(i)
    evaluated_at = _utc(d.get('evaluated_at'))
    checks = {
        'decision_timestamp_valid': decision_at is not None,
        'evidence_timestamps_valid': not invalid,
        'no_future_evidence': not future,
        'outcome_not_known_at_decision': evaluated_at is None or (decision_at is not None and evaluated_at > decision_at),
        'historical_not_forward_maturity': d.get('forward_maturity_source') in (None, 'PROSPECTIVE_PAPER'),
        'automatic_promotion_blocked': d.get('automatic_promotion', False) is False,
        'real_trading_frozen': d.get('real_trading', False) is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {'status': 'PASS' if not blockers else 'FAIL', 'checks': checks, 'blockers': blockers,
            'future_evidence_indexes': future, 'invalid_evidence_indexes': invalid, 'real_trading': False}


def learning_closure_gate(episode: dict[str, Any] | None):
    e = episode or {}; action = str(e.get('action') or '').upper()
    decision_at = _utc(e.get('decision_at') or e.get('created_at'))
    evaluated_at = _utc(e.get('evaluated_at'))
    abstain = action.startswith('ABSTAIN') or action == 'HOLD'
    outcome_closed = bool(e.get('outcome')) or abstain
    checks = {
        'decision_id_present': bool(e.get('decision_id') or e.get('episode_id')),
        'agent_present': bool(e.get('agent_id')),
        'signal_present': bool(e.get('signal') or e.get('signal_family') or e.get('reason')),
        'regime_present': bool(e.get('regime')),
        'horizon_present': bool(e.get('horizon')),
        'action_present': bool(action),
        'closed_or_explicit_abstention': outcome_closed,
        'evaluation_after_decision': abstain or (decision_at is not None and evaluated_at is not None and evaluated_at > decision_at),
        'lesson_or_abstention_reason': bool(e.get('lesson') or e.get('reason')),
        'automatic_promotion_blocked': e.get('automatic_promotion', False) is False,
        'real_trading_frozen': e.get('real_trading', False) is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {'status': 'PASS' if not blockers else 'FAIL', 'checks': checks, 'blockers': blockers,
            'abstention': abstain, 'real_trading': False}


def simulator_autonomous_gate(*, base_gate: dict[str, Any] | None,
                              restore: dict[str, Any] | None,
                              session: dict[str, Any] | None,
                              simulator: dict[str, Any] | None,
                              control: dict[str, Any] | None,
                              lease: dict[str, Any] | None,
                              market: dict[str, Any] | None,
                              temporal_probe: dict[str, Any] | None,
                              learning_probe: dict[str, Any] | None,
                              now: Any = None):
    base = base_gate or {}
    sub = {
        'base_simulator_gate': {'status': 'PASS' if base.get('status') == 'SIMULATOR_READY' else 'FAIL'},
        'exact_persistent_restore': exact_restore_gate(restore),
        'autonomous_session_continuity': continuity_gate(session=session, simulator=simulator, control=control,
                                                         lease=lease, now=now),
        'market_data_point_in_time': market_snapshot_gate(market, now=now),
        'temporal_learning_isolation': temporal_isolation_gate(temporal_probe),
        'learning_loop_closure': learning_closure_gate(learning_probe),
    }
    blockers = [name for name, result in sub.items() if result.get('status') != 'PASS']
    return {'status': 'PASS' if not blockers else 'FAIL', 'checks': sub, 'blockers': blockers,
            'paper_execution_allowed': not blockers, 'live_execution_allowed': False,
            'automatic_promotion': False, 'automatic_release': False, 'setup_1_6_allowed': False,
            'real_trading': False}
