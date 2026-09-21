from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class StartupWatchdogReportV3:
    state: str
    elapsed_seconds: float
    deadline_seconds: float
    provider_required: bool
    process_alive: bool
    status_url_seen: bool
    health_confirmed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StartupWatchdogV3:
    """Core-local boot watchdog. Provider availability can never consume the activation deadline."""

    def __init__(self, *, deadline_seconds: float = 45.0):
        self.started = time.monotonic()
        self.deadline_seconds = max(5.0, float(deadline_seconds))
        self.status_url_seen = False
        self.health_confirmed = False
        self.last_reason = "waiting_for_core_health"

    def observe(self, *, process_alive: bool, status_url_seen: bool = False, health_confirmed: bool = False, reason: str = "") -> StartupWatchdogReportV3:
        self.status_url_seen = self.status_url_seen or bool(status_url_seen)
        self.health_confirmed = self.health_confirmed or bool(health_confirmed)
        if reason:
            self.last_reason = str(reason)[:500]
        elapsed = time.monotonic() - self.started
        if self.health_confirmed:
            state = "HEALTHY"
        elif not process_alive:
            state = "PROCESS_EXITED"
        elif elapsed >= self.deadline_seconds:
            state = "CORE_HEALTH_TIMEOUT"
        else:
            state = "WAITING"
        return StartupWatchdogReportV3(
            state=state, elapsed_seconds=round(elapsed, 3), deadline_seconds=self.deadline_seconds,
            provider_required=False, process_alive=bool(process_alive), status_url_seen=self.status_url_seen,
            health_confirmed=self.health_confirmed, reason=self.last_reason,
        )
