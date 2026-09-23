"""Radar desktop v5 — launch-oriented PAPER home screen.

Pure presentation/view-model layer. It consumes existing PAPER telemetry and has
no execution, promotion, release, maturity, broker, or live-trading authority.
"""
from __future__ import annotations

import radar_simulation_desktop_v4 as v4
from radar_observable_paper_v1 import observable_snapshot

REAL_TRADING = False


def _money(value):
    try:
        return f"{float(value):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _value(value):
    return "—" if value is None else str(value)


def launch_home_model(simulator=None, equity=None):
    """Stable, read-only contract for the main Windows screen."""
    snap = observable_snapshot(simulator or {}, equity or {}, metric="equity", window="today")
    s = snap["summary"]
    safety = snap["safety"]
    return {
        "title": "Radar de inversión",
        "mode_banner": "PAPER · REAL_TRADING OFF 🔒",
        "safety": safety,
        "cards": {
            "equity": _money(s.get("equity")),
            "cash": _money(s.get("cash")),
            "pnl_today": _money(s.get("pnl_today")),
            "pnl_total": _money(s.get("pnl_total")),
            "open_positions": int(s.get("open_positions") or 0),
        },
        "engine": {
            "runtime": _value(s.get("runtime_status")),
            "last_cycle": _value(s.get("last_cycle")),
            "autonomy": "PAPER",
        },
        "activity": snap["activity"],
        "read_only": True,
        "warning": None if safety.get("real_trading") is False else "SAFETY STATE INVALID",
    }


class LaunchHome(v4.ExplainableVScoreLab):
    """Existing cockpit plus a launch home summary; no engine mutations."""

    def __init__(self, root):
        super().__init__(root)
        try:
            root.title("Radar de inversión · PAPER")
        except Exception:
            pass

    def launch_snapshot(self):
        return launch_home_model(getattr(self, "cloud_simulator", {}) or {}, {})


def main():
    v4.base.ensure_agents()
    v4.base.champion_status()
    root = v4.base.tk.Tk()
    LaunchHome(root)
    root.mainloop()


if __name__ == "__main__":
    main()
