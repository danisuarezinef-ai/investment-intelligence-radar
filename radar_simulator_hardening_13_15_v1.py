"""Fail-closed PAPER hardening contracts for priorities 13-15.

13. Daily prospective PAPER result ledger with timestamped hypothetical trades.
14. Persistent historical memory integrity and monotonic learning history.
15. Autonomous learning/decision gate with evidence sufficiency, bounded adaptation,
    explicit abstention and no live-trading authority.

These contracts do not place orders, enable real trading, promote models, or release builds.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from json import dumps
from typing import Any, Iterable

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


def _stable_hash(payload: Any) -> str:
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def daily_paper_result_gate(day: dict[str, Any] | None):
    """Validate one immutable prospective PAPER day.

    Every hypothetical trade must be timestamped, linked to a decision, and marked PAPER.
    Backfill, missing timestamps, impossible ordering, or missing accounting identity fail closed.
    """
    d = dict(day or {})
    date = str(d.get("date") or "")
    opened_at = _utc(d.get("opened_at"))
    closed_at = _utc(d.get("closed_at"))
    trades = list(d.get("trades") or [])
    valid_trades = []
    trade_errors = []
    last_ts = None
    for i, raw in enumerate(trades):
        t = dict(raw or {}) if isinstance(raw, dict) else {}
        ts = _utc(t.get("ts"))
        decision_at = _utc(t.get("decision_at"))
        errs = []
        if not t.get("trade_id"): errs.append("trade_id")
        if not t.get("decision_id"): errs.append("decision_id")
        if not t.get("symbol"): errs.append("symbol")
        if str(t.get("side") or "").upper() not in {"BUY", "SELL"}: errs.append("side")
        if ts is None: errs.append("timestamp")
        if decision_at is None: errs.append("decision_timestamp")
        if ts is not None and decision_at is not None and ts < decision_at: errs.append("trade_before_decision")
        if last_ts is not None and ts is not None and ts < last_ts: errs.append("non_monotonic_trade_time")
        if t.get("paper") is not True: errs.append("paper_marker")
        if t.get("backfilled") is True: errs.append("backfilled")
        if t.get("real_trading", False) is not False: errs.append("real_trading")
        if not isinstance(t.get("quantity"), (int, float)) or float(t.get("quantity")) <= 0: errs.append("quantity")
        if not isinstance(t.get("fill_price"), (int, float)) or float(t.get("fill_price")) <= 0: errs.append("fill_price")
        if errs:
            trade_errors.append({"index": i, "errors": errs})
        else:
            valid_trades.append(t)
            last_ts = ts

    start_equity = d.get("start_equity")
    end_equity = d.get("end_equity")
    net_pnl = d.get("net_pnl")
    accounting_identity = (
        isinstance(start_equity, (int, float))
        and isinstance(end_equity, (int, float))
        and isinstance(net_pnl, (int, float))
        and abs((float(start_equity) + float(net_pnl)) - float(end_equity)) <= 1e-6
    )
    checks = {
        "date_present": bool(date),
        "prospective_paper": d.get("evidence_class") == "PROSPECTIVE_PAPER",
        "opened_timestamp_valid": opened_at is not None,
        "closed_timestamp_valid": closed_at is not None,
        "day_order_valid": opened_at is not None and closed_at is not None and closed_at > opened_at,
        "no_backfill": d.get("backfilled") is False,
        "all_trades_valid": not trade_errors,
        "accounting_identity": accounting_identity,
        "daily_summary_hash_present": bool(d.get("summary_hash")),
        "immutable": d.get("immutable") is True,
        "real_trading_frozen": d.get("real_trading", False) is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {
        "status": "PASS_DAILY_PAPER" if not blockers else "BLOCKED_DAILY_PAPER",
        "checks": checks,
        "blockers": blockers,
        "trade_errors": trade_errors,
        "valid_trade_count": len(valid_trades),
        "daily_record_hash": _stable_hash({k: d.get(k) for k in sorted(d) if k != "daily_record_hash"}),
        "paper_execution_allowed": not blockers,
        "live_execution_allowed": False,
        "real_trading": False,
    }


def memory_integrity_gate(memory: dict[str, Any] | None):
    """Require append-only, ordered, hashed PAPER memory with provenance."""
    m = dict(memory or {})
    entries = list(m.get("entries") or [])
    seen_ids = set()
    previous_ts = None
    invalid = []
    for i, raw in enumerate(entries):
        e = dict(raw or {}) if isinstance(raw, dict) else {}
        errs = []
        eid = e.get("memory_id")
        ts = _utc(e.get("created_at"))
        if not eid: errs.append("memory_id")
        elif eid in seen_ids: errs.append("duplicate_memory_id")
        if eid: seen_ids.add(eid)
        if ts is None: errs.append("created_at")
        if previous_ts is not None and ts is not None and ts < previous_ts: errs.append("non_monotonic_time")
        if ts is not None: previous_ts = ts
        if e.get("source_type") not in {"DECISION", "OUTCOME", "ABSTENTION", "MARKET_OBSERVATION", "LESSON"}:
            errs.append("source_type")
        if not e.get("source_id"): errs.append("source_id")
        if not e.get("content_hash"): errs.append("content_hash")
        if e.get("backfilled") is True: errs.append("backfilled")
        if e.get("deleted") is True or e.get("mutated") is True: errs.append("append_only_violation")
        if e.get("real_trading", False) is not False: errs.append("real_trading")
        if errs: invalid.append({"index": i, "errors": errs})

    checks = {
        "schema_version_present": bool(m.get("schema_version")),
        "memory_store_id_present": bool(m.get("memory_store_id")),
        "append_only": m.get("append_only") is True,
        "entries_valid": not invalid,
        "checkpoint_hash_present": bool(m.get("checkpoint_hash")),
        "exact_restore_required": m.get("exact_restore_required") is True,
        "backfill_forbidden": m.get("backfill_allowed") is False,
        "real_trading_frozen": m.get("real_trading", False) is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    return {
        "status": "PASS_MEMORY_INTEGRITY" if not blockers else "BLOCKED_MEMORY_INTEGRITY",
        "checks": checks,
        "blockers": blockers,
        "invalid_entries": invalid,
        "entry_count": len(entries),
        "memory_fingerprint": _stable_hash(entries),
        "learning_allowed": not blockers,
        "silent_memory_rewrite_allowed": False,
        "real_trading": False,
    }


def autonomous_learning_gate(*, candidate: dict[str, Any] | None,
                             memory_gate: dict[str, Any] | None,
                             daily_gate: dict[str, Any] | None,
                             max_parameter_delta: float = 0.10,
                             min_forward_observations: int = 20,
                             min_confidence: float = 0.60):
    """Bound autonomous adaptation to PAPER-only, forward evidence and small deltas."""
    c = dict(candidate or {})
    mem = memory_gate or {}
    day = daily_gate or {}
    proposed_delta = abs(float(c.get("max_parameter_delta") or 0.0))
    confidence = float(c.get("confidence") or 0.0)
    forward_n = int(c.get("forward_observations") or 0)
    action = str(c.get("action") or "ABSTAIN").upper()
    checks = {
        "memory_integrity_pass": mem.get("status") == "PASS_MEMORY_INTEGRITY",
        "daily_evidence_pass": day.get("status") == "PASS_DAILY_PAPER",
        "prospective_forward_only": c.get("evidence_class") == "PROSPECTIVE_PAPER" and c.get("forward_only") is True,
        "no_backfill": c.get("backfilled") is False,
        "minimum_forward_observations": forward_n >= int(min_forward_observations),
        "confidence_sufficient": confidence >= float(min_confidence),
        "bounded_parameter_delta": proposed_delta <= float(max_parameter_delta),
        "parameter_bounds_respected": c.get("parameter_bounds_respected") is True,
        "risk_gate_cannot_be_bypassed": c.get("can_bypass_risk_gate") is False,
        "promotion_gate_cannot_be_bypassed": c.get("can_bypass_promotion_gate") is False,
        "human_review_for_model_replacement": c.get("automatic_model_replacement") is False,
        "real_trading_frozen": c.get("real_trading", False) is False,
    }
    blockers = [k for k, v in checks.items() if not v]
    abstain = bool(blockers) or action == "ABSTAIN"
    return {
        "status": "ABSTAIN_LEARNING" if abstain else "PASS_BOUNDED_PAPER_LEARNING",
        "action": "ABSTAIN" if abstain else action,
        "checks": checks,
        "blockers": blockers,
        "forward_observations": forward_n,
        "confidence": confidence,
        "max_parameter_delta": proposed_delta,
        "learning_update_allowed": not abstain,
        "paper_decision_allowed": not abstain,
        "automatic_model_replacement": False,
        "automatic_promotion": False,
        "live_execution_allowed": False,
        "real_trading": False,
    }


def priorities_13_15_gate(*, daily: dict[str, Any] | None,
                          memory: dict[str, Any] | None,
                          learning: dict[str, Any] | None):
    sub = {
        "daily_paper_results": daily or {},
        "persistent_memory": memory or {},
        "bounded_autonomous_learning": learning or {},
    }
    checks = {
        "daily": sub["daily_paper_results"].get("status") == "PASS_DAILY_PAPER",
        "memory": sub["persistent_memory"].get("status") == "PASS_MEMORY_INTEGRITY",
        "learning": sub["bounded_autonomous_learning"].get("status") in {"PASS_BOUNDED_PAPER_LEARNING", "ABSTAIN_LEARNING"},
        "no_live": all(x.get("real_trading", False) is False for x in sub.values()),
    }
    blockers = [k for k, v in checks.items() if not v]
    return {
        "status": "PASS" if not blockers else "FAIL",
        "checks": checks,
        "blockers": blockers,
        "paper_runtime_supported": not blockers,
        "automatic_promotion": False,
        "automatic_release": False,
        "live_execution_allowed": False,
        "setup_1_6_allowed": False,
        "real_trading": False,
    }
