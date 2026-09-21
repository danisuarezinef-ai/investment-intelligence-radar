from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .browser_lifecycle import BrowserLifecyclePolicy, BrowserPressureDetector
from .models import ProjectState


@dataclass(slots=True)
class BrowserProfileState:
    name: str
    active: int
    suspended: int
    rss_mb: float
    throughput: float
    recycle_recommended: bool
    reason: str


class BrowserOrchestrator:
    """Coordinates browser profile pools without owning credentials or session secrets."""

    def __init__(self) -> None:
        self.pressure = BrowserPressureDetector()
        self.lifecycle = BrowserLifecyclePolicy()

    def assess_service(self, state: ProjectState, name: str, *, active: int, suspended: int = 0, rss_mb: float = 0.0, throughput: float = 0.0, previous_workers: int | None = None, previous_throughput: float | None = None) -> BrowserProfileState:
        ram_limit = float(state.metadata.get("browser_ram_budget_mb", 0) or 0) or None
        decision = self.pressure.assess(workers=active, throughput=throughput, previous_workers=previous_workers, previous_throughput=previous_throughput, ram_limit_mb=ram_limit)
        payload = BrowserProfileState(name, active, suspended, round(rss_mb, 2), round(throughput, 4), decision.recycle, decision.reason)
        state.metadata.setdefault("browser_orchestration", {})[name] = asdict(payload)
        return payload

    def desired_profiles(self, state: ProjectState, service: str, max_profiles: int = 64) -> int:
        base = max(1, round(max_profiles * state.power_percent / 100))
        service_stats = state.metadata.get("browser_orchestration", {}).get(service, {})
        if service_stats.get("recycle_recommended"):
            base = max(1, base // 2)
        return min(max_profiles, base)

    def suspended_descriptor(self, conversation_id: str, url: str, profile_dir: str) -> dict[str, Any]:
        return self.lifecycle.suspend_descriptor(conversation_id, url, profile_dir)
