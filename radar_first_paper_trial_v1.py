"""First official end-to-end PAPER trial contracts (Blocks E-H).

This module is deliberately fail-closed. It never fabricates quotes, outcomes, fills or
forward maturity. It consumes observed records from existing Radar components and only
marks a gate ready when the supplied evidence satisfies the contract.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable

REAL_TRADING = False
TRIAL_ID = "RADAR_FIRST_PAPER_TRIAL_001"
AGENTS = ("conservative","balanced","aggressive","high_conviction","experimental")
HORIZONS = ("1d","1w","1m","3m")
FROZEN_UNIVERSE = (
    "MSFT","NVDA","GOOGL","AMZN","META","AVGO","ASML","SAP","TSM","TM","SHEL","RIO",
    "LLY","V","BRK-B","NVS","AAPL","JPM","XOM","UNH","COST","AMD","NFLX","ORCL",
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def market_data_gate(quotes: Iterable[dict], *, now_iso: str | None = None,
                     max_age_seconds: int = 900) -> dict:
    """Validate observed quote provenance/freshness without inventing bid/ask."""
    now = _dt(now_iso) if now_iso else datetime.now(timezone.utc)
    by_symbol = {}
    rejected = []
    for raw in quotes:
        q = dict(raw); symbol = str(q.get("symbol") or "").upper()
        reasons = []
        try:
            price = float(q.get("price"));
            if price <= 0: reasons.append("non_positive_price")
        except Exception: reasons.append("invalid_price")
        try:
            age = max(0.0, (now - _dt(q.get("observed_at") or q.get("ts"))).total_seconds())
            if age > max_age_seconds: reasons.append("stale_quote")
        except Exception:
            age = None; reasons.append("invalid_timestamp")
        if not q.get("provider") and not q.get("source"): reasons.append("missing_provider")
        if symbol not in FROZEN_UNIVERSE: reasons.append("outside_frozen_universe")
        if reasons:
            rejected.append({"symbol":symbol or None,"reasons":reasons,"age_seconds":age})
        elif symbol:
            q["age_seconds"] = age
            q["bid_ask_observed"] = q.get("bid") is not None and q.get("ask") is not None
            by_symbol[symbol] = q
    missing = [s for s in FROZEN_UNIVERSE if s not in by_symbol]
    ready = not missing and not rejected
    return {"status":"READY" if ready else "NOT_READY","accepted":len(by_symbol),
            "universe_size":len(FROZEN_UNIVERSE),"missing":missing,"rejected":rejected,
            "bid_ask_coverage":sum(1 for q in by_symbol.values() if q["bid_ask_observed"]),
            "frozen_universe":list(FROZEN_UNIVERSE),"real_trading":False}


def validate_agent_decision(decision: dict) -> dict:
    d = dict(decision); missing=[]
    required=("agent","symbol","action","conviction","horizon","observed_price","thesis","factors","risks","invalidation")
    for k in required:
        if d.get(k) in (None,"",[]): missing.append(k)
    if d.get("agent") not in AGENTS: missing.append("valid_agent")
    if str(d.get("action") or "").upper() not in {"BUY","HOLD","SELL","ABSTAIN"}: missing.append("valid_action")
    if d.get("horizon") not in HORIZONS: missing.append("valid_horizon")
    try:
        c=float(d.get("conviction"));
        if not 0 <= c <= 1: missing.append("conviction_0_1")
    except Exception: missing.append("conviction_0_1")
    return {"status":"PASS" if not missing else "FAIL","missing":sorted(set(missing)),"decision":d,"real_trading":False}


def opportunity_369(decisions: Iterable[dict]) -> dict:
    valid=[dict(x) for x in decisions if validate_agent_decision(x)["status"]=="PASS" and str(x.get("action")).upper()!="ABSTAIN"]
    valid.sort(key=lambda x:(float(x.get("conviction",0)), float(x.get("expected_return",0) or 0)), reverse=True)
    unique=[]; seen=set()
    for x in valid:
        s=x["symbol"]
        if s not in seen: seen.add(s); unique.append(x)
    return {"top3_high_confidence":unique[:3],"top6_risk_return":sorted(unique,key=lambda x:float(x.get("risk_adjusted_score",x.get("conviction",0)) or 0),reverse=True)[:6],
            "top9_promising":unique[:9],"abstentions":[dict(x) for x in decisions if str(x.get("action")).upper()=="ABSTAIN"],"real_trading":False}


def ensemble(decisions: Iterable[dict]) -> dict:
    rows=[dict(x) for x in decisions if validate_agent_decision(x)["status"]=="PASS"]
    grouped={}
    for x in rows: grouped.setdefault(x["symbol"],[]).append(x)
    out=[]
    for symbol, ds in grouped.items():
        votes={a:sum(1 for d in ds if str(d["action"]).upper()==a) for a in ("BUY","HOLD","SELL","ABSTAIN")}
        winner=max(votes,key=votes.get); disagreement=1-(votes[winner]/max(1,len(ds)))
        if disagreement>=0.6: winner="ABSTAIN"
        out.append({"symbol":symbol,"action":winner,"votes":votes,"disagreement":round(disagreement,4),
                    "mean_conviction":round(sum(float(d["conviction"]) for d in ds)/len(ds),4)})
    return {"status":"READY" if out else "NO_DECISIONS","decisions":out,"real_trading":False}


def end_to_end_link(decision: dict, order: dict | None, fill: dict | None, position: dict | None) -> dict:
    did=decision.get("decision_id"); oid=(order or {}).get("order_id"); fid=(fill or {}).get("fill_id")
    reasons=[]
    if not did: reasons.append("missing_decision_id")
    if order is None: reasons.append("not_executed")
    elif order.get("decision_id") != did: reasons.append("order_decision_link_mismatch")
    if fill is not None and fill.get("order_id") != oid: reasons.append("fill_order_link_mismatch")
    if position is not None and position.get("origin_decision_id") != did: reasons.append("position_origin_link_mismatch")
    return {"status":"VERIFIED" if not reasons else "NOT_VERIFIED","decision_id":did,"order_id":oid,"fill_id":fid,
            "reasons":reasons,"paper_only":True,"broker_submit_enabled":False,"real_trading":False}


def learning_contract() -> dict:
    return {"status":"ACTIVE_CONTRACT","agents":list(AGENTS),"horizons":list(HORIZONS),
            "learn_from_abstention":True,"champion_challenger":True,"paper_internal_promotion_allowed":True,
            "mutation_policy":"small_traceable","genealogy_required":True,"hall_of_fame":True,"graveyard":True,
            "anti_overfitting_score_required":True,"historical_live_transfer_required":True,
            "provisional_short_horizon_evidence_must_not_be_labeled_forward_mature":True,
            "real_trading":False}


def trial_manifest(*, git_sha: str, initial_capital: float, risk_rules: dict) -> dict:
    if initial_capital <= 0: raise ValueError("initial_capital must be positive")
    return {"trial_id":TRIAL_ID,"git_sha":git_sha,"initial_capital":float(initial_capital),
            "universe":list(FROZEN_UNIVERSE),"agents":list(AGENTS),"horizons":list(HORIZONS),
            "risk_rules":dict(risk_rules),"benchmarks":["cash","buy_and_hold","appropriate_index","equal_weight"],
            "restart_recovery_required":True,"exact_checkpoint_continuity_required":True,
            "metrics":["return","excess_return","drawdown","volatility","turnover","costs","exposure","confidence_calibration","hit_rate","payoff","sharpe_if_sample_sufficient","sortino_if_sample_sufficient"],
            "paper_only":True,"real_trading":False}


def trial_report(manifest: dict, *, technical_checks: dict, metrics: dict, decisions: list[dict], lessons: list[dict]) -> dict:
    hard=("market_data","paper_accounting","persistence","decision_execution_linkage","restart_recovery")
    failed=[k for k in hard if technical_checks.get(k) is not True]
    verdict="FAIL" if failed else ("REPEAT" if not metrics else "PASS")
    return {"trial_id":manifest.get("trial_id"),"verdict":verdict,"failed_checks":failed,
            "metrics":dict(metrics),"decisions_recorded":len(decisions),"lessons":list(lessons),
            "next_trial":"RADAR_PAPER_TRIAL_002" if verdict in {"PASS","REPEAT"} else None,
            "automatic_real_money_transition":False,"real_trading":False}
