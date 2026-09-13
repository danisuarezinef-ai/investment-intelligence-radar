"""Production recovery supervisor v11 for the autonomous PAPER runtime.

V11 decouples process health from PAPER admission. The HTTP process can be healthy while
persistent authority is unavailable, but every mutating endpoint and all PAPER workers
remain blocked until the exact persisted session, distributed lease, and exact PAPER
checkpoint restore are proven. It never reconstructs or backfills state and cannot enable
live trading, broker submission, automatic promotion/release, or Setup 1.6.
"""
from __future__ import annotations

import os
import threading
import time
from http.server import ThreadingHTTPServer

import cloud_service_v10 as base10
import cloud_service_v9 as base9
import cloud_service_v4 as base4
import run_worker

REAL_TRADING = False
_LOCK = threading.RLock()
_STATE = {
    "status": "STARTING_BLOCKED",
    "attempts": 0,
    "last_attempt_at": None,
    "last_error": None,
    "runtime_started": False,
    "worker_started": False,
    "session_id": None,
    "lease": None,
    "paper_restore": None,
    "backfill_used": False,
    "reconstructed": False,
    "real_trading": False,
}
_WORKER_THREAD = None


def _strict_persisted_session_id() -> str:
    """Require the previously persisted PAPER session; never mint one during recovery."""
    try:
        item = base9.autonomous_paper._remote_latest(base9.autonomous_paper.SESSION_KIND)
        payload = (item or {}).get("payload") if isinstance(item, dict) else None
        session_id = str((payload or {}).get("session_id") or "").strip() if isinstance(payload, dict) else ""
        return session_id
    except Exception:
        return ""


def admission_status():
    with _LOCK:
        out = dict(_STATE)
    out.update({
        "paper_execution_allowed": out.get("status") == "READY_EXACT_PAPER",
        "live_execution_allowed": False,
        "broker_submit_enabled": False,
        "automatic_promotion": False,
        "automatic_release": False,
        "setup_1_6_allowed": False,
        "backfill_allowed": False,
        "reconstruction_allowed": False,
        "real_trading": False,
    })
    return out


def _block(reason: str, *, lease=None, paper_restore=None):
    try:
        base9.autonomous_paper.simulator.set_enabled(False)
    except Exception:
        pass
    with _LOCK:
        _STATE.update({
            "status": "BLOCKED_EXACT_RECOVERY",
            "last_error": str(reason)[:900],
            "lease": lease,
            "paper_restore": paper_restore,
            "runtime_started": False,
            "real_trading": False,
        })


def _release_current_lease():
    with base10._LEASE_LOCK:
        owner = base10._LEASE_STATE.get("owner_id")
        session = base10._LEASE_STATE.get("session_id")
    if owner and session:
        try:
            base10.runtime_lease.release(str(owner), str(session))
        except Exception:
            pass


def _start_core_worker(runtime):
    global _WORKER_THREAD
    with _LOCK:
        if _STATE.get("worker_started"):
            return
        _STATE["worker_started"] = True
    t = threading.Thread(target=runtime.run_worker.worker_loop, name="radar-core-worker-v11", daemon=True)
    _WORKER_THREAD = t
    t.start()


def attempt_exact_admission():
    """One bounded admission attempt. Failure leaves the service healthy but PAPER blocked."""
    with _LOCK:
        _STATE["attempts"] = int(_STATE.get("attempts") or 0) + 1
        _STATE["last_attempt_at"] = time.time()
        _STATE["last_error"] = None

    session_id = _strict_persisted_session_id()
    with _LOCK:
        _STATE["session_id"] = session_id or None
    if not session_id:
        _block("persisted PAPER session unavailable; refusing to mint replacement session")
        return admission_status()

    # Force v10 to use only the verified persisted session during this admission.
    base10._session_id = lambda: session_id
    lease = base10.acquire_runtime_lease()
    if lease.get("held") is not True:
        _block("distributed PAPER lease not held", lease=lease)
        return admission_status()

    try:
        runtime = base10.start_runtime()
        paper_restore = dict(base9.base8.base7.base6.base5.base4.base3._PAPER_ENGINE_STATUS)
        exact = (
            paper_restore.get("status") == "RESTORED_EXACT_PAPER_ENGINE"
            and paper_restore.get("verified") is True
            and paper_restore.get("remote_state_hash")
            and paper_restore.get("remote_state_hash") == paper_restore.get("local_state_hash")
            and paper_restore.get("backfill_used") is False
            and paper_restore.get("reconstructed") is False
            and paper_restore.get("real_trading") is False
        )
        if not exact:
            raise RuntimeError(f"exact PAPER restore not proven: {paper_restore.get('status')}")
        runtime.run_worker._Handler = ValidationV11Handler
        _start_core_worker(runtime)
        with _LOCK:
            _STATE.update({
                "status": "READY_EXACT_PAPER",
                "runtime_started": True,
                "last_error": None,
                "lease": lease,
                "paper_restore": paper_restore,
                "backfill_used": False,
                "reconstructed": False,
                "real_trading": False,
            })
        return admission_status()
    except Exception as exc:
        # cloud_service_v4 marks itself started before the exact restore. Reset only that
        # guard so a later recovery attempt can genuinely repeat the exact restore path.
        try:
            base4._V4_RUNTIME_STARTED = False
        except Exception:
            pass
        _release_current_lease()
        _block(f"{type(exc).__name__}: {str(exc)[:800]}", lease=lease)
        return admission_status()


def _recovery_loop():
    while True:
        with _LOCK:
            ready = _STATE.get("status") == "READY_EXACT_PAPER"
        if not ready:
            try:
                attempt_exact_admission()
            except Exception as exc:
                _block(f"recovery loop: {type(exc).__name__}: {str(exc)[:700]}")
        time.sleep(30)


class ValidationV11Handler(base10.ValidationV10Handler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            state = admission_status()
            self._send(200, {
                "ok": True,
                "service": "Investment Intelligence Radar Cloud",
                "runtime": "v11-health-first-fail-closed",
                "admission": state,
                "paper_execution_allowed": state["paper_execution_allowed"],
                "live_execution_allowed": False,
                "automatic_promotion": False,
                "automatic_release": False,
                "setup_1_6_allowed": False,
                "real_trading": False,
            })
            return
        if path == "/autonomous-simulator/admission-v1":
            self._send(200, admission_status()); return
        if admission_status().get("status") != "READY_EXACT_PAPER":
            self._send(503, {
                "status": "BLOCKED_EXACT_RECOVERY",
                "reason": admission_status().get("last_error"),
                "paper_execution_allowed": False,
                "live_execution_allowed": False,
                "automatic_promotion": False,
                "automatic_release": False,
                "setup_1_6_allowed": False,
                "real_trading": False,
            })
            return
        super().do_GET()

    def do_POST(self):
        if admission_status().get("status") != "READY_EXACT_PAPER":
            self._send(503, {
                "status": "BLOCKED_EXACT_RECOVERY",
                "paper_execution_allowed": False,
                "live_execution_allowed": False,
                "automatic_promotion": False,
                "automatic_release": False,
                "setup_1_6_allowed": False,
                "real_trading": False,
            })
            return
        super().do_POST()


def main():
    threading.Thread(target=_recovery_loop, name="paper-exact-recovery-v11", daemon=True).start()
    port = int(os.environ.get("PORT") or 0)
    if port <= 0:
        while True:
            time.sleep(60)
    ThreadingHTTPServer(("0.0.0.0", port), ValidationV11Handler).serve_forever()


if __name__ == "__main__":
    main()
