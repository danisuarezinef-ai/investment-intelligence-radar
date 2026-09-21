from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
import time

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class CircuitState:
    component: str
    state: str
    failures: int
    open_until: float
    reason: str
    at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IncidentManagerV2:
    """Bounded incident history + provider/application circuit breakers."""

    KEY = "incident_manager_v2"

    def _root(self, state: ProjectState) -> dict[str, Any]:
        return state.metadata.setdefault(self.KEY, {"components": {}, "history": []})

    def allowed(self, state: ProjectState, component: str, *, now: float | None = None) -> bool:
        ts = time.time() if now is None else float(now)
        row = self._root(state)["components"].get(component) or {}
        if row.get("state") == "open" and ts >= float(row.get("open_until", 0.0) or 0.0):
            row["state"] = "half_open"
            row["half_open_probe_available"] = True
        if row.get("state") == "open":
            return False
        if row.get("state") == "half_open":
            if row.get("half_open_probe_available"):
                row["half_open_probe_available"] = False
                return True
            return False
        return True

    def record_failure(self, state: ProjectState, component: str, reason: str, *, threshold: int = 3, cooldown_seconds: int = 30, now: float | None = None) -> CircuitState:
        ts = time.time() if now is None else float(now)
        root = self._root(state); row = root["components"].setdefault(component, {"state":"closed", "failures":0, "open_until":0.0})
        row["failures"] = int(row.get("failures", 0) or 0) + 1
        if row["failures"] >= max(1, threshold):
            row["state"] = "open"; row["open_until"] = ts + max(1, cooldown_seconds); row["half_open_probe_available"] = False
        row["reason"] = str(reason)[:500]; row["updated_at"] = _now()
        event = {"component":component,"event":"failure","reason":row["reason"],"state":row["state"],"ts":row["updated_at"]}
        root["history"].append(event); del root["history"][:-1000]
        return CircuitState(component, row["state"], row["failures"], float(row.get("open_until",0.0)), row["reason"], row["updated_at"])

    def record_success(self, state: ProjectState, component: str) -> CircuitState:
        root = self._root(state); row = root["components"].setdefault(component, {})
        row.update({"state":"closed", "failures":0, "open_until":0.0, "reason":"recovered", "half_open_probe_available":False, "updated_at":_now()})
        root["history"].append({"component":component,"event":"recovered","ts":row["updated_at"]}); del root["history"][:-1000]
        return CircuitState(component, "closed", 0, 0.0, "recovered", row["updated_at"])
