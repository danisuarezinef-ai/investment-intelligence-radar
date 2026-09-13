"""Closure contracts for the next 10 simulator tasks.

These contracts turn earlier hardening primitives into runtime-verifiable PAPER-only
requirements. They never authorize live trading, broker submission, promotion,
release, or Setup 1.6.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
import math

REAL_TRADING = False


def _utc(v: Any):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None
    return d.astimezone(timezone.utc) if d.tzinfo else None


def learning_scorecard(metrics: dict[str, Any] | None, *, min_ratio_n: int = 30):
    """Task 1: evidence-aware Autonomous PAPER Learning Scorecard."""
    m = metrics or {}
    required = ["uptime_pct", "valid_forward_hours", "cycles", "decisions", "trades", "abstentions",
                "gross_pnl", "net_pnl", "max_drawdown", "turnover", "costs", "errors", "recoveries",
                "persistence_integrity", "historical_to_paper_transfer"]
    missing = [k for k in required if k not in m]
    n = int(m.get("return_observations", 0) or 0)
    sharpe = m.get("sharpe") if n >= min_ratio_n else None
    sortino = m.get("sortino") if n >= min_ratio_n else None
    breakdowns = m.get("breakdowns") or {}
    checks = {
        "required_metrics": not missing,
        "breakdown_agents": isinstance(breakdowns.get("agents"), dict),
        "breakdown_regimes": isinstance(breakdowns.get("regimes"), dict),
        "breakdown_horizons": isinstance(breakdowns.get("horizons"), dict),
        "persistence_integrity": m.get("persistence_integrity") is True,
        "real_trading_frozen": m.get("real_trading") is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {"status": "SCORECARD_VALID" if not blockers else "SCORECARD_PARTIAL",
            "checks": checks, "missing": missing, "sharpe": sharpe, "sortino": sortino,
            "ratio_sample_status": "ENOUGH_DATA" if n >= min_ratio_n else "NOT_ENOUGH_DATA",
            "financial_performance_does_not_authorize_live": True,
            "live_execution_allowed": False, "real_trading": False}


def disaster_recovery_matrix(rows: Iterable[dict[str, Any]] | None):
    """Task 2: destructive PAPER recovery matrix."""
    required = {"process_kill", "partial_order_restart", "railway_redeploy", "supabase_outage",
                "supabase_timeout", "price_provider_failure", "corrupt_price", "stale_price",
                "invalid_symbol", "duplicate_message", "duplicate_instance", "restart_mid_persist"}
    data = {str(r.get("scenario")): r for r in (rows or []) if isinstance(r, dict)}
    missing = sorted(required - set(data))
    invalid = []
    for name in sorted(required & set(data)):
        r = data[name]
        outcome = r.get("outcome")
        if outcome not in {"EXACT_RECOVERY", "FAIL_CLOSED"}:
            invalid.append(name); continue
        if outcome == "EXACT_RECOVERY":
            if not all(r.get(k) is True for k in ("state_hash_equal", "accounting_reconciled", "no_duplicate_orders")):
                invalid.append(name)
        if r.get("real_trading") is not False:
            invalid.append(name)
    blockers = [f"missing:{x}" for x in missing] + [f"invalid:{x}" for x in sorted(set(invalid))]
    return {"status": "PASS" if not blockers else "FAIL", "blockers": blockers,
            "scenarios_checked": sorted(required & set(data)), "live_execution_allowed": False,
            "real_trading": False}


def distributed_singleton_gate(lease: dict[str, Any] | None, *, owner_id: str, session_id: str, now: Any = None):
    """Task 3/4: durable singleton/lease state must be fresh and uniquely owned."""
    l = lease or {}; n = _utc(now) or datetime.now(timezone.utc); exp = _utc(l.get("expires_at")); hb = _utc(l.get("heartbeat_at"))
    checks = {
        "lease_name": l.get("lease_name") == "autonomous-paper",
        "owner": l.get("owner_id") == owner_id,
        "session": l.get("session_id") == session_id,
        "fresh": bool(exp and hb and exp > n and hb <= n),
        "epoch": isinstance(l.get("epoch"), int) and l.get("epoch", 0) >= 1,
        "real_trading_frozen": l.get("real_trading") is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {"status": "HELD" if not blockers else "BLOCKED", "checks": checks, "blockers": blockers,
            "second_runtime_allowed": False, "real_trading": False}


def runtime_wiring_gate(gates: dict[str, dict[str, Any]] | None):
    """Task 5: prove runtime cannot bypass any mandatory gate."""
    required = ["restore", "continuity", "lease", "market", "execution", "risk", "accounting", "learning", "maturity"]
    g = gates or {}; missing = [x for x in required if x not in g]
    allowed = {"PASS", "HELD", "RECONCILED", "VALID_FORWARD_CLOCK", "RESTORED_EXACT_PAPER_ENGINE",
               "PASS_PAPER_RISK", "FILLED", "PARTIAL_FILL", "ABSTAIN", "LEARN_PAPER"}
    failed = [x for x in required if x in g and str(g[x].get("status")) not in allowed]
    blockers = [f"missing:{x}" for x in missing] + [f"failed:{x}" for x in failed]
    return {"status": "RUNTIME_CHAIN_PASS" if not blockers else "RUNTIME_CHAIN_BLOCKED",
            "blockers": blockers, "paper_cycle_allowed": not blockers,
            "live_execution_allowed": False, "real_trading": False}


def market_pipeline_gate(snapshot: dict[str, Any] | None, *, now: Any = None, max_age_seconds: int = 120):
    """Task 6: point-in-time market pipeline integrity."""
    s = snapshot or {}; obs = _utc(s.get("observed_at")); n = _utc(now) or datetime.now(timezone.utc)
    age = (n - obs).total_seconds() if obs and n >= obs else None
    checks = {
        "symbol": bool(s.get("symbol")), "provider": bool(s.get("provider")),
        "timestamp_utc": obs is not None, "fresh": age is not None and age <= max_age_seconds,
        "price_positive": isinstance(s.get("price"), (int, float)) and math.isfinite(float(s.get("price"))) and float(s.get("price")) > 0,
        "market_open_known": isinstance(s.get("market_open"), bool),
        "no_duplicate": s.get("duplicate") is not True, "no_gap": s.get("silent_gap") is not True,
        "not_stale": s.get("stale") is not True, "point_in_time_hash": bool(s.get("snapshot_hash")),
        "real_trading_frozen": s.get("real_trading") is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {"status": "PASS" if not blockers else "FAIL", "checks": checks, "blockers": blockers,
            "age_seconds": age, "live_execution_allowed": False, "real_trading": False}


def execution_realism_gate(x: dict[str, Any] | None):
    """Task 7: PAPER fills must include realistic execution frictions."""
    e = x or {}
    checks = {
        "spread": isinstance(e.get("spread_bps"), (int, float)) and float(e.get("spread_bps")) >= 0,
        "slippage": isinstance(e.get("slippage_bps"), (int, float)) and float(e.get("slippage_bps")) >= 0,
        "fees": isinstance(e.get("fees"), (int, float)) and float(e.get("fees")) >= 0,
        "liquidity": isinstance(e.get("available_volume"), (int, float)) and float(e.get("available_volume")) >= 0,
        "partial_fill_modeled": isinstance(e.get("partial_fill_modeled"), bool),
        "reject_cancel_modeled": e.get("rejects_modeled") is True and e.get("cancels_modeled") is True,
        "market_hours_enforced": e.get("market_hours_enforced") is True,
        "gap_risk_modeled": e.get("gap_risk_modeled") is True,
        "size_vs_volume_checked": e.get("size_vs_volume_checked") is True,
        "real_trading_frozen": e.get("real_trading") is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {"status": "PASS" if not blockers else "FAIL", "checks": checks, "blockers": blockers,
            "live_execution_allowed": False, "real_trading": False}


def accounting_source_of_truth(account: dict[str, Any] | None, *, tolerance: float = 1e-6):
    """Task 8: exact PAPER accounting identities, no silent correction."""
    a = account or {}
    nums = {k: a.get(k) for k in ("cash", "positions_value", "equity", "realized_pnl", "unrealized_pnl", "costs", "total_pnl")}
    numeric = all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in nums.values())
    if not numeric:
        return {"status": "CRITICAL_RECONCILIATION_FAILURE", "blockers": ["non_numeric"],
                "silent_correction_allowed": False, "new_paper_risk_allowed": False, "real_trading": False}
    eq_error = abs(float(a["cash"]) + float(a["positions_value"]) - float(a["equity"]))
    pnl_error = abs(float(a["realized_pnl"]) + float(a["unrealized_pnl"]) - float(a["costs"]) - float(a["total_pnl"]))
    ok = eq_error <= tolerance and pnl_error <= tolerance and a.get("real_trading") is False
    return {"status": "RECONCILED" if ok else "CRITICAL_RECONCILIATION_FAILURE",
            "equity_error": eq_error, "pnl_error": pnl_error, "silent_correction_allowed": False,
            "new_paper_risk_allowed": ok, "live_execution_allowed": False, "real_trading": False}


def restart_reconciliation_gate(restore: dict[str, Any] | None, reconciliation: dict[str, Any] | None):
    """Task 9: no PAPER continuation after restart until exact restore+reconciliation."""
    r = restore or {}; c = reconciliation or {}
    checks = {
        "exact_restore": r.get("status") == "RESTORED_EXACT_PAPER_ENGINE" and r.get("verified") is True,
        "hash_equal": bool(r.get("remote_state_hash")) and r.get("remote_state_hash") == r.get("local_state_hash"),
        "no_backfill": r.get("backfill_used") is False and r.get("reconstructed") is False,
        "session_preserved": r.get("session_id_before") == r.get("session_id_after") and bool(r.get("session_id_after")),
        "accounting_reconciled": c.get("status") == "RECONCILED",
        "real_trading_frozen": r.get("real_trading") is False and c.get("real_trading") is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {"status": "PASS" if not blockers else "FAIL_CLOSED", "checks": checks, "blockers": blockers,
            "paper_resume_allowed": not blockers, "live_execution_allowed": False, "real_trading": False}


def downstream_hard_lock(state: dict[str, Any] | None):
    """Task 10: PAPER success must never unlock live/promote/release/Setup 1.6."""
    s = state or {}
    forbidden_true = [k for k in ("real_trading", "broker_submit_enabled", "live_execution_allowed",
                                   "automatic_promotion", "automatic_release", "setup_1_6_allowed") if s.get(k) is True]
    checks = {"forbidden_capabilities_false": not forbidden_true,
              "paper_only": s.get("mode") in {None, "PAPER", "SIMULATION_ONLY"},
              "explicit_release_authority_absent": s.get("release_authority") in {None, False, "NONE"}}
    blockers = [k for k, v in checks.items() if not v] + [f"forbidden:{x}" for x in forbidden_true]
    return {"status": "LOCKED" if not blockers else "CRITICAL_BLOCK", "checks": checks, "blockers": blockers,
            "real_trading": False, "broker_submit_enabled": False, "live_execution_allowed": False,
            "automatic_promotion": False, "automatic_release": False, "setup_1_6_allowed": False}
