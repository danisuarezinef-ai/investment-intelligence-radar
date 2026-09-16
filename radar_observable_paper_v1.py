"""Read-only observability helpers for the autonomous PAPER engine.

Consumes already-produced PAPER telemetry. It deliberately exposes no execution,
promotion, release or maturity authority and never mutates engine state.
"""
from __future__ import annotations
from datetime import datetime, timezone

ALLOWED_WINDOWS=("today","week","month","3m","all")
ALLOWED_METRICS=("equity","pnl","operations","opportunities","confidence")

def _f(value,default=0.0):
    try:return float(value)
    except (TypeError,ValueError):return default

def activity_stage(row):
    raw=str((row or {}).get("stage") or (row or {}).get("status") or (row or {}).get("action") or "observed").lower()
    if any(x in raw for x in ("buy","sell","execute","filled","trade")):return "PAPER_ACTION"
    if any(x in raw for x in ("candidate","opportunity","rank","shortlist")):return "OPPORTUNITY"
    if any(x in raw for x in ("reject","discard","skip","blocked")):return "DISCARDED"
    return "ANALYZING"

def build_live_activity(simulator):
    simulator=simulator or {};source=list(simulator.get("activity") or simulator.get("recent_activity") or simulator.get("recent_decisions") or [])
    out=[]
    for row in source[:80]:
        if not isinstance(row,dict):continue
        out.append({"ts":row.get("ts") or row.get("timestamp") or row.get("completed_at") or row.get("started_at"),
                    "symbol":row.get("symbol") or row.get("asset") or row.get("ticker") or "—","stage":activity_stage(row),
                    "action":row.get("side") or row.get("action") or row.get("decision") or "OBSERVE",
                    "confidence":row.get("confidence") if row.get("confidence") is not None else row.get("score"),
                    "reason":str(row.get("reason") or row.get("rationale") or row.get("summary") or "")[:280],
                    "agent":row.get("agent") or row.get("strategy") or row.get("competitor_key") or "—","paper_only":True})
    return out

def portfolio_summary(simulator):
    paper=(simulator or {}).get("paper") or {};positions=list(paper.get("positions") or (simulator or {}).get("positions") or [])
    return {"mode":"PAPER","real_trading":False,"equity":paper.get("equity",paper.get("total")),"cash":paper.get("cash"),
            "pnl_today":paper.get("pnl_today"),"pnl_total":paper.get("pnl_total"),"open_positions":len(positions),
            "last_cycle":(simulator or {}).get("completed_cycles"),"runtime_status":(simulator or {}).get("status") or ("ACTIVE" if (simulator or {}).get("active") else "UNKNOWN")}

def timeline(equity_payload,simulator,metric="equity"):
    if metric not in ALLOWED_METRICS:metric="equity"
    if metric in ("equity","pnl"):
        series=list((equity_payload or {}).get("series") or (equity_payload or {}).get("daily_equity_30d") or []);out=[];first=None
        for row in series:
            if not isinstance(row,dict):continue
            value=_f(row.get("equity",row.get("normalized_equity")),None)
            if value is None:continue
            if first is None:first=value
            out.append({"ts":row.get("ts") or row.get("date") or row.get("day"),"value":value if metric=="equity" else value-first})
        return out
    activity=build_live_activity(simulator)
    if metric=="operations":return [x for x in activity if x["stage"]=="PAPER_ACTION"]
    if metric=="opportunities":return [x for x in activity if x["stage"]=="OPPORTUNITY"]
    if metric=="confidence":return [{"ts":x["ts"],"value":_f(x.get("confidence"),0.0),"symbol":x["symbol"]} for x in activity if x.get("confidence") is not None]
    return activity

def observable_snapshot(simulator=None,equity=None,metric="equity",window="today"):
    if window not in ALLOWED_WINDOWS:window="today"
    metric=metric if metric in ALLOWED_METRICS else "equity"
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"safety":{"mode":"PAPER","real_trading":False,"read_only":True},
            "window":window,"metric":metric,"summary":portfolio_summary(simulator or {}),"activity":build_live_activity(simulator or {}),
            "timeline":timeline(equity or {},simulator or {},metric),"note":"Display telemetry only; no maturity, promotion, release or trading authority."}
