"""Fail-closed contracts for autonomous PAPER priorities 16-25.

This module composes continuity, disaster recovery, reconciliation, decision journaling,
forward evaluation, attribution, meta-learning and scorecard contracts. It never enables
live trading, broker submission, automatic promotion, release or Setup 1.6.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
import math

REAL_TRADING = False


def _utc(value: Any):
    if value in (None, ""):
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
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


def distributed_lease_gate(lease: dict[str, Any] | None, *, expected_session_id: str | None = None,
                           now: Any = None, max_heartbeat_age_seconds: int = 180):
    """Priority 16: require one fresh, unexpired durable PAPER lease."""
    l = lease or {}
    now_dt = _utc(now) if now is not None else datetime.now(timezone.utc)
    expires = _utc(l.get("expires_at"))
    heartbeat_age = _age_seconds(l.get("heartbeat_at"), now_dt)
    checks = {
        "singleton_name": l.get("lease_name") == "autonomous-paper",
        "owner_present": bool(l.get("owner_id")),
        "session_present": bool(l.get("session_id")),
        "session_matches": expected_session_id in (None, l.get("session_id")),
        "epoch_valid": isinstance(l.get("epoch"), int) and l.get("epoch", 0) >= 1,
        "heartbeat_fresh": heartbeat_age is not None and heartbeat_age <= max_heartbeat_age_seconds,
        "not_expired": expires is not None and now_dt is not None and expires > now_dt,
        "real_trading_frozen": l.get("real_trading") is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {"status": "PASS" if not blockers else "FAIL", "checks": checks,
            "blockers": blockers, "heartbeat_age_seconds": heartbeat_age,
            "live_execution_allowed": False, "real_trading": False}


def end_to_end_runtime_gate(*, gates: dict[str, dict[str, Any]] | None):
    """Priority 17: one fail-closed chain from evidence to learning persistence."""
    required = [
        "restore", "continuity", "lease", "market_data", "temporal_isolation",
        "risk", "abstention", "paper_execution", "accounting", "learning",
        "persistence", "maturity",
    ]
    g = gates or {}
    missing = [name for name in required if name not in g]
    failed = [name for name in required if name in g and str(g[name].get("status")) not in {
        "PASS", "PASS_PAPER_RISK", "RECONCILED", "VALID_FORWARD_CLOCK", "FILLED", "PARTIAL_FILL",
        "ABSTAIN", "LEARN_PAPER", "RESTORED_EXACT_PAPER_ENGINE"
    }]
    blockers = [f"missing:{x}" for x in missing] + [f"failed:{x}" for x in failed]
    return {
        "status": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "paper_cycle_allowed": not blockers,
        "live_execution_allowed": False,
        "automatic_promotion": False,
        "automatic_release": False,
        "setup_1_6_allowed": False,
        "real_trading": False,
    }


def watchdog_recovery_gate(runtime: dict[str, Any] | None, *, now: Any = None,
                           max_heartbeat_age_seconds: int = 180,
                           max_cycle_age_seconds: int = 900):
    """Priority 18: classify runtime health and permit only exact PAPER recovery."""
    r = runtime or {}
    hb_age = _age_seconds(r.get("heartbeat_at"), now)
    cycle_age = _age_seconds(r.get("last_cycle_at"), now)
    unhealthy = []
    if hb_age is None or hb_age > max_heartbeat_age_seconds:
        unhealthy.append("heartbeat_stale")
    if cycle_age is None or cycle_age > max_cycle_age_seconds:
        unhealthy.append("cycle_stalled")
    if r.get("hung") is True:
        unhealthy.append("hung_process")
    if int(r.get("consecutive_errors", 0) or 0) >= int(r.get("max_consecutive_errors", 3) or 3):
        unhealthy.append("error_threshold")
    exact = bool(r.get("exact_checkpoint_available")) and bool(r.get("checkpoint_hash_verified"))
    duplicate_safe = r.get("distributed_lease_held") is True
    if unhealthy:
        status = "AUTO_RECOVER_EXACT_PAPER" if exact and duplicate_safe else "FAIL_CLOSED"
    else:
        status = "HEALTHY"
    return {
        "status": status,
        "health_failures": unhealthy,
        "restart_allowed": status == "AUTO_RECOVER_EXACT_PAPER",
        "restart_mode": "EXACT_PAPER_ONLY" if status == "AUTO_RECOVER_EXACT_PAPER" else None,
        "maturity_reset_required": False,
        "maturity_downtime_counts": False,
        "live_execution_allowed": False,
        "real_trading": False,
    }


def disaster_test_gate(results: Iterable[dict[str, Any]] | None):
    """Priority 19: require destructive scenarios to prove exact recovery or safe failure."""
    required = {
        "process_kill", "redeploy_mid_position", "supabase_outage", "market_data_outage",
        "corrupt_response", "timeout", "duplicate_delivery", "duplicate_instance",
    }
    rows = list(results or [])
    by_name = {str(x.get("scenario")): x for x in rows if isinstance(x, dict)}
    missing = sorted(required - set(by_name))
    bad = []
    for name in sorted(required & set(by_name)):
        r = by_name[name]
        if r.get("result") not in {"EXACT_RECOVERY", "FAIL_CLOSED"}:
            bad.append(name)
        elif r.get("result") == "EXACT_RECOVERY" and not (
            r.get("state_hash_equal") is True and r.get("session_continuity") is True
        ):
            bad.append(name)
        if r.get("real_trading") is not False:
            bad.append(name)
    blockers = [f"missing:{x}" for x in missing] + [f"invalid:{x}" for x in sorted(set(bad))]
    return {"status": "PASS" if not blockers else "FAIL", "blockers": blockers,
            "covered": sorted(set(by_name) & required), "live_execution_allowed": False,
            "real_trading": False}


def persistence_reconciliation_gate(local: dict[str, Any] | None, remote: dict[str, Any] | None):
    """Priority 20: exact local<->remote source-of-truth reconciliation."""
    a, b = local or {}, remote or {}
    keys = ["state_hash", "session_id", "cycle", "cash", "equity", "positions_hash", "learning_hash"]
    mismatches = [k for k in keys if a.get(k) != b.get(k)]
    freshness_ok = _utc(a.get("observed_at")) is not None and _utc(b.get("observed_at")) is not None
    checks = {
        "identity": not mismatches,
        "timestamps_valid": freshness_ok,
        "local_not_backfilled": a.get("backfilled") is not True,
        "remote_not_backfilled": b.get("backfilled") is not True,
        "real_trading_frozen": a.get("real_trading") is False and b.get("real_trading") is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    if mismatches:
        blockers.append("state_mismatch")
    return {
        "status": "RECONCILED" if not blockers else "CRITICAL_PERSISTENCE_DIVERGENCE",
        "mismatched_fields": mismatches, "blockers": blockers,
        "silent_overwrite_allowed": False, "new_paper_risk_allowed": not blockers,
        "live_execution_allowed": False, "real_trading": False,
    }


def decision_journal_gate(entry: dict[str, Any] | None):
    """Priority 21: prove what was known, who voted and why the PAPER action occurred."""
    e = entry or {}
    decision_at = _utc(e.get("decision_at"))
    votes = list(e.get("agent_votes") or [])
    evidence = list(e.get("evidence") or [])
    future_evidence = []
    for i, item in enumerate(evidence):
        ts = _utc(item.get("known_at") if isinstance(item, dict) else None)
        if ts is None or decision_at is None or ts > decision_at:
            future_evidence.append(i)
    checks = {
        "decision_id": bool(e.get("decision_id")),
        "decision_time": decision_at is not None,
        "action": str(e.get("action") or "").upper() in {"BUY", "SELL", "HOLD", "ABSTAIN"},
        "confidence": isinstance(e.get("confidence"), (int, float)) and 0 <= float(e.get("confidence")) <= 1,
        "regime": bool(e.get("regime")),
        "horizon": e.get("horizon") in {"1d", "1w", "1m", "3m"},
        "votes_present": bool(votes),
        "risk_snapshot": isinstance(e.get("risk"), dict),
        "causal_thesis": bool(e.get("causal_thesis")),
        "decision_reason": bool(e.get("reason")),
        "no_future_evidence": not future_evidence,
        "real_trading_frozen": e.get("real_trading") is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {"status": "PASS" if not blockers else "FAIL", "checks": checks,
            "blockers": blockers, "future_evidence_indexes": future_evidence,
            "live_execution_allowed": False, "real_trading": False}


def forward_horizon_evaluator(decision: dict[str, Any] | None, outcomes: Iterable[dict[str, Any]] | None,
                              *, now: Any = None):
    """Priority 22: mature outcomes independently at 1d/1w/1m/3m without lookahead."""
    d = decision or {}
    decision_at = _utc(d.get("decision_at"))
    now_dt = _utc(now) if now is not None else datetime.now(timezone.utc)
    horizon_hours = {"1d": 24, "1w": 24 * 7, "1m": 24 * 30, "3m": 24 * 90}
    indexed = {str(x.get("horizon")): x for x in (outcomes or []) if isinstance(x, dict)}
    report = {}
    for h, hours in horizon_hours.items():
        mature = bool(decision_at and now_dt and (now_dt - decision_at).total_seconds() >= hours * 3600)
        row = indexed.get(h)
        valid = bool(row and _utc(row.get("evaluated_at")) and _utc(row.get("evaluated_at")) > decision_at) if decision_at else False
        report[h] = {
            "mature": mature,
            "status": "EVALUATED" if mature and valid else ("PENDING" if not mature else "MISSING_OR_INVALID"),
            "return": row.get("return") if mature and valid else None,
            "benchmark_return": row.get("benchmark_return") if mature and valid else None,
        }
    return {"status": "PASS" if decision_at else "FAIL", "horizons": report,
            "unmatured_outcomes_used": False, "live_execution_allowed": False,
            "real_trading": False}


def attribution_gate(attribution: dict[str, Any] | None, *, tolerance: float = 1e-9):
    """Priority 23: require additive P&L attribution identity."""
    a = attribution or {}
    components = ["signal", "regime", "selection", "timing", "sizing", "costs", "residual"]
    vals = {}
    valid = True
    for k in components:
        v = a.get(k)
        if not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            valid = False
            vals[k] = 0.0
        else:
            vals[k] = float(v)
    total = a.get("total_return")
    total_valid = isinstance(total, (int, float)) and math.isfinite(float(total))
    identity_error = abs(sum(vals.values()) - float(total)) if total_valid else None
    checks = {
        "components_numeric": valid,
        "total_numeric": total_valid,
        "identity": identity_error is not None and identity_error <= tolerance,
        "costs_non_positive": vals["costs"] <= 0,
        "residual_bounded": abs(vals["residual"]) <= float(a.get("max_abs_residual", 0.05)),
    }
    blockers = [k for k, v in checks.items() if not v]
    return {"status": "PASS" if not blockers else "FAIL", "checks": checks,
            "identity_error": identity_error, "blockers": blockers,
            "live_execution_allowed": False, "real_trading": False}


def meta_learning_gate(candidate: dict[str, Any] | None, *, max_parameter_delta: float = 0.05,
                       min_forward_n: int = 50, min_forward_regimes: int = 2):
    """Priority 24: permit only bounded challenger mutation in SHADOW/PAPER."""
    c = candidate or {}
    deltas = dict(c.get("parameter_deltas") or {})
    numeric = all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in deltas.values())
    bounded = numeric and all(abs(float(v)) <= max_parameter_delta for v in deltas.values())
    checks = {
        "challenger_only": c.get("role") == "challenger",
        "prospective_forward": c.get("forward_only") is True and c.get("backfilled") is not True,
        "sample": int(c.get("forward_n", 0) or 0) >= min_forward_n,
        "regime_diversity": len(set(c.get("forward_regimes") or [])) >= min_forward_regimes,
        "parameter_deltas_numeric": numeric,
        "parameter_deltas_bounded": bounded,
        "lineage_present": bool(c.get("lineage_id")) and bool(c.get("parent_lineage_id")),
        "no_champion_mutation": c.get("mutates_active_champion") is not True,
        "no_auto_promotion": c.get("automatic_promotion") is not True,
        "real_trading_frozen": c.get("real_trading") is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {"status": "ELIGIBLE_SHADOW_PAPER" if not blockers else "REJECTED",
            "checks": checks, "blockers": blockers, "automatic_promotion": False,
            "automatic_replacement": False, "live_execution_allowed": False,
            "real_trading": False}


def autonomous_paper_scorecard(metrics: dict[str, Any] | None, *, min_sharpe_n: int = 30):
    """Priority 25: canonical PAPER operating scorecard with evidence-aware metrics."""
    m = metrics or {}
    n = int(m.get("return_observations", 0) or 0)
    sharpe = m.get("sharpe") if n >= min_sharpe_n else None
    sortino = m.get("sortino") if n >= min_sharpe_n else None
    required = ["uptime_pct", "cycles", "decisions", "trades", "abstentions", "equity",
                "pnl", "max_drawdown", "costs", "errors", "recoveries",
                "persistence_integrity", "valid_forward_hours"]
    missing = [k for k in required if k not in m]
    critical = []
    if m.get("persistence_integrity") is not True:
        critical.append("persistence_integrity")
    if m.get("accounting_integrity", True) is not True:
        critical.append("accounting_integrity")
    if m.get("duplicate_instance_detected") is True:
        critical.append("duplicate_instance")
    milestones = {
        "72h": "PASS" if float(m.get("valid_forward_hours", 0) or 0) >= 72 else "PENDING",
        "7d": "PASS" if float(m.get("valid_forward_hours", 0) or 0) >= 168 else "PENDING",
        "30d": "PASS" if float(m.get("valid_forward_hours", 0) or 0) >= 720 else "PENDING",
    }
    return {
        "status": "CRITICAL" if critical else ("COMPLETE" if not missing else "INCOMPLETE"),
        "missing_metrics": missing, "critical_failures": critical,
        "metrics": {**m, "sharpe": sharpe, "sortino": sortino},
        "milestones": milestones,
        "sharpe_sortino_sample_adequate": n >= min_sharpe_n,
        "live_execution_allowed": False, "automatic_promotion": False,
        "automatic_release": False, "setup_1_6_allowed": False,
        "real_trading": False,
    }


def priorities_16_25_gate(*, lease: dict[str, Any], runtime_chain: dict[str, Any],
                          watchdog: dict[str, Any], disasters: dict[str, Any],
                          reconciliation: dict[str, Any], journal: dict[str, Any],
                          horizons: dict[str, Any], attribution: dict[str, Any],
                          meta_learning: dict[str, Any], scorecard: dict[str, Any]):
    checks = {
        "lease": lease.get("status") == "PASS",
        "runtime_chain": runtime_chain.get("status") == "PASS",
        "watchdog": watchdog.get("status") in {"HEALTHY", "AUTO_RECOVER_EXACT_PAPER"},
        "disasters": disasters.get("status") == "PASS",
        "reconciliation": reconciliation.get("status") == "RECONCILED",
        "journal": journal.get("status") == "PASS",
        "horizons": horizons.get("status") == "PASS",
        "attribution": attribution.get("status") == "PASS",
        "meta_learning": meta_learning.get("status") in {"ELIGIBLE_SHADOW_PAPER", "REJECTED"},
        "scorecard": scorecard.get("status") in {"COMPLETE", "INCOMPLETE"},
    }
    blockers = [k for k, v in checks.items() if not v]
    return {"status": "PASS" if not blockers else "FAIL", "checks": checks,
            "blockers": blockers, "paper_runtime_hardened": not blockers,
            "live_execution_allowed": False, "automatic_promotion": False,
            "automatic_release": False, "setup_1_6_allowed": False,
            "real_trading": False}
