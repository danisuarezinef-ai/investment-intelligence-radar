"""Production entrypoint v10: v9 plus fail-closed simulator closure wiring.

V10 adds a durable Supabase singleton lease before the autonomous PAPER control plane
is allowed to start, continuously heartbeats that lease, and exposes closure health.
It does not enable live trading, broker submission, automatic promotion/release, or
Setup 1.6.
"""
from __future__ import annotations

import threading
import time

import cloud_service_v9 as base9
import radar_paper_runtime_lease_v1 as runtime_lease
import radar_simulator_closure_26_35_v1 as closure

REAL_TRADING = False
_LEASE_LOCK = threading.RLock()
_LEASE_STATE = {"owner_id": None, "session_id": None, "last": None, "last_error": None, "started": False}
_HEARTBEAT_STARTED = False


def _session_id():
    try:
        return str(base9.autonomous_paper._load_or_create_session().get("session_id") or "")
    except Exception:
        return ""


def acquire_runtime_lease():
    owner = runtime_lease.owner_id(); session = _session_id()
    if not session:
        out = {"status": "BLOCKED", "held": False, "reason": "missing_session_id", "real_trading": False}
    else:
        out = runtime_lease.acquire(owner, session, ttl_seconds=180)
    with _LEASE_LOCK:
        _LEASE_STATE.update({"owner_id": owner, "session_id": session, "last": out,
                             "last_error": out.get("error"), "started": out.get("held") is True})
    return out


def heartbeat_runtime_lease():
    with _LEASE_LOCK:
        owner = _LEASE_STATE.get("owner_id"); session = _LEASE_STATE.get("session_id")
    if not owner or not session:
        return acquire_runtime_lease()
    out = runtime_lease.heartbeat(str(owner), str(session), ttl_seconds=180)
    if out.get("held") is not True:
        # Fail closed: losing the distributed lease disables PAPER immediately.
        try: base9.autonomous_paper.simulator.set_enabled(False)
        except Exception: pass
    with _LEASE_LOCK:
        _LEASE_STATE["last"] = out; _LEASE_STATE["last_error"] = out.get("error")
    return out


def _heartbeat_loop():
    while True:
        try: heartbeat_runtime_lease()
        except Exception as exc:
            with _LEASE_LOCK: _LEASE_STATE["last_error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
            try: base9.autonomous_paper.simulator.set_enabled(False)
            except Exception: pass
        time.sleep(60)


def _ensure_heartbeat():
    global _HEARTBEAT_STARTED
    with _LEASE_LOCK:
        if _HEARTBEAT_STARTED: return
        _HEARTBEAT_STARTED = True
        threading.Thread(target=_heartbeat_loop, name="paper-runtime-lease-heartbeat", daemon=True).start()


def lease_status():
    with _LEASE_LOCK: local = dict(_LEASE_STATE)
    remote = runtime_lease.status()
    lease = remote.get("lease") or {}
    gate = closure.distributed_singleton_gate(lease, owner_id=str(local.get("owner_id") or ""),
                                              session_id=str(local.get("session_id") or ""))
    return {"local": local, "remote": remote, "gate": gate, "real_trading": False}


def downstream_lock_status():
    return closure.downstream_hard_lock({
        "mode": "PAPER", "real_trading": False, "broker_submit_enabled": False,
        "live_execution_allowed": False, "automatic_promotion": False,
        "automatic_release": False, "setup_1_6_allowed": False, "release_authority": "NONE",
    })


def closure_status():
    lease = lease_status(); sim = base9.autonomous_paper.simulator.simulator_status(); paper = sim.get("paper") or {}
    account = closure.accounting_source_of_truth({
        "cash": float(paper.get("cash") or 0.0),
        "positions_value": float(paper.get("invested") or 0.0),
        "equity": float(paper.get("total") or 0.0),
        "realized_pnl": float(paper.get("realized_pnl") or 0.0),
        "unrealized_pnl": float(paper.get("unrealized_pnl") or 0.0),
        "costs": float(paper.get("costs") or 0.0),
        "total_pnl": float(paper.get("total_pnl") or ((paper.get("realized_pnl") or 0.0) + (paper.get("unrealized_pnl") or 0.0) - (paper.get("costs") or 0.0))),
        "real_trading": False,
    })
    return {
        "status": "PASS" if lease.get("gate", {}).get("status") == "HELD" and account.get("status") == "RECONCILED" else "BLOCKED",
        "lease": lease, "accounting": account, "watchdog": base9.autonomous_paper.watchdog_status(),
        "milestones": base9.autonomous_paper.milestones(), "downstream_lock": downstream_lock_status(),
        "paper_execution_allowed": lease.get("gate", {}).get("status") == "HELD" and account.get("status") == "RECONCILED",
        "live_execution_allowed": False, "automatic_promotion": False, "automatic_release": False,
        "setup_1_6_allowed": False, "real_trading": False,
    }


class ValidationV10Handler(base9.ValidationV9Handler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/autonomous-simulator/lease-v1": self._send(200, lease_status()); return
            if path == "/autonomous-simulator/closure-v1": self._send(200, closure_status()); return
            if path == "/autonomous-simulator/downstream-lock-v1": self._send(200, downstream_lock_status()); return
        except Exception as exc:
            self._send(500, {"status": "FAIL_CLOSED", "error": str(exc)[:800],
                             "live_execution_allowed": False, "automatic_promotion": False,
                             "automatic_release": False, "setup_1_6_allowed": False, "real_trading": False}); return
        super().do_GET()


def start_runtime():
    lease = acquire_runtime_lease()
    if lease.get("held") is not True:
        # Prevent the v9 control plane from enabling the PAPER daemon if singleton ownership is not proven.
        base9.autonomous_paper.ensure_started = lambda: {"status": "BLOCKED_DISTRIBUTED_LEASE", "real_trading": False}
        try: base9.autonomous_paper.simulator.set_enabled(False)
        except Exception: pass
    runtime = base9.start_runtime()
    runtime.run_worker._Handler = ValidationV10Handler
    _ensure_heartbeat()
    return runtime


if __name__ == "__main__":
    runtime = start_runtime(); runtime.run_worker.main()
