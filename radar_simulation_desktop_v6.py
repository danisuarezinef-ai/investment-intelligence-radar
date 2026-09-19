"""Radar desktop v6 — explainable PAPER activity and visual timeline contracts.

Presentation only. Filters/selectors never mutate engine, maturity, policy,
promotion, release or execution state. REAL_TRADING remains disabled.
"""
from __future__ import annotations
from collections import Counter
import radar_simulation_desktop_v5 as v5
from radar_observable_paper_v1 import observable_snapshot, ALLOWED_WINDOWS, ALLOWED_METRICS

REAL_TRADING=False
STAGE_ORDER=("ANALYZING","OPPORTUNITY","DISCARDED","PAPER_ACTION")
WINDOW_LABELS={"today":"Hoy","week":"Semana","month":"Mes","3m":"3 meses","all":"Todo"}
METRIC_LABELS={"equity":"Cartera PAPER","pnl":"P&L","operations":"Operaciones","opportunities":"Oportunidades","confidence":"Confianza"}


def thinking_model(simulator=None):
    """Explain what Radar observed without turning an opportunity into a trade."""
    snap=observable_snapshot(simulator or {}, {}, metric="opportunities", window="today")
    rows=snap["activity"]
    counts=Counter(r["stage"] for r in rows)
    return {
        "pipeline":[{"stage":s,"count":counts.get(s,0)} for s in STAGE_ORDER],
        "items":[{
            "ts":r.get("ts"),"symbol":r.get("symbol"),"stage":r.get("stage"),
            "action":r.get("action"),"confidence":r.get("confidence"),
            "reason":r.get("reason") or "—","agent":r.get("agent") or "—",
            "paper_only":True,
        } for r in rows],
        "opportunity_is_trade":False,
        "read_only":True,
    }


def chart_model(simulator=None,equity=None,metric="equity",window="today"):
    """Single main-chart model. Window/metric are presentation selectors only."""
    if metric not in ALLOWED_METRICS: metric="equity"
    if window not in ALLOWED_WINDOWS: window="today"
    snap=observable_snapshot(simulator or {},equity or {},metric=metric,window=window)
    actions=[x for x in snap["activity"] if x["stage"]=="PAPER_ACTION"]
    markers=[{
        "ts":x.get("ts"),"symbol":x.get("symbol"),"side":x.get("action"),
        "reason":x.get("reason"),"confidence":x.get("confidence"),
        "agent":x.get("agent"),"paper_only":True,
    } for x in actions]
    return {
        "title":"Actividad de inversión",
        "window":window,"window_label":WINDOW_LABELS[window],
        "metric":metric,"metric_label":METRIC_LABELS[metric],
        "series":snap["timeline"],"trade_markers":markers,
        "selectors":{"windows":list(ALLOWED_WINDOWS),"metrics":list(ALLOWED_METRICS)},
        "read_only":True,"maturity_credit":False,
    }


def launch_dashboard_model(simulator=None,equity=None,metric="equity",window="today"):
    return {
        "home":v5.launch_home_model(simulator,equity),
        "thinking":thinking_model(simulator),
        "chart":chart_model(simulator,equity,metric,window),
        "mode_banner":"PAPER · REAL_TRADING OFF 🔒",
        "read_only":True,
    }


class ExplainableLaunchHome(v5.LaunchHome):
    def thinking_snapshot(self):
        return thinking_model(getattr(self,"cloud_simulator",{}) or {})
    def chart_snapshot(self,metric="equity",window="today"):
        return chart_model(getattr(self,"cloud_simulator",{}) or {},{},metric,window)


def main():
    v5.v4.base.ensure_agents()
    v5.v4.base.champion_status()
    root=v5.v4.base.tk.Tk()
    ExplainableLaunchHome(root)
    root.mainloop()

if __name__=="__main__":
    main()
