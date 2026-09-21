from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .device_fabric import AdaptiveDeviceFabric, DeviceProfile
from .models import ProjectState, Task


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class DeviceTelemetry:
    device_id: str
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    battery_percent: float | None = None
    charging: bool = False
    thermal_state: str = "nominal"  # nominal|warm|hot|critical
    network_score: float = 1.0


class DeviceResourceFabricV2:
    KEY = "device_resource_fabric_v2"
    MOBILE_ALLOWED_TASK_KINDS = {"reasoning", "summarize", "embedding", "code_review", "batch_tests", "research", "local_model", "general"}

    def __init__(self) -> None:
        self.fabric = AdaptiveDeviceFabric()

    def report(self, state: ProjectState, telemetry: DeviceTelemetry) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {}).setdefault("telemetry", {})
        row[telemetry.device_id] = {**asdict(telemetry), "reported_at": _now()}
        return row[telemetry.device_id]

    def can_accept(self, state: ProjectState, task: Task, device: DeviceProfile) -> dict[str, Any]:
        tele = ((state.metadata.get(self.KEY) or {}).get("telemetry") or {}).get(device.device_id, {})
        thermal = str(tele.get("thermal_state") or "nominal").lower()
        battery = tele.get("battery_percent", device.battery_percent)
        if thermal in {"hot", "critical"}:
            return {"allowed": False, "reason": f"thermal_{thermal}"}
        if battery is not None and float(battery) < 15 and not bool(tele.get("charging", False)):
            return {"allowed": False, "reason": "low_battery"}
        if float(tele.get("ram_percent", 0.0) or 0.0) >= 92:
            return {"allowed": False, "reason": "ram_pressure"}
        if float(tele.get("cpu_percent", 0.0) or 0.0) >= 95:
            return {"allowed": False, "reason": "cpu_pressure"}
        kind = str(task.metadata.get("task_kind") or "general").lower()
        if device.kind == "mobile" and kind not in self.MOBILE_ALLOWED_TASK_KINDS:
            return {"allowed": False, "reason": "mobile_scope_restricted"}
        return {"allowed": True, "reason": "capacity_available"}

    def choose(self, state: ProjectState, task: Task) -> dict[str, Any]:
        self.fabric.initialize_windows(state)
        ranked = []
        for device in self.fabric.profiles(state):
            admission = self.can_accept(state, task, device)
            if not admission["allowed"]:
                continue
            score = self.fabric.score(task, device, state.power_percent)
            if score != float("-inf"):
                ranked.append((score, device))
        if not ranked:
            return {"device_id": None, "reason": "no_admitted_device"}
        ranked.sort(key=lambda x: x[0], reverse=True)
        score, device = ranked[0]
        return {"device_id": device.device_id, "kind": device.kind, "score": round(float(score), 4), "reason": "admitted_highest_score"}

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        tele = ((state.metadata.get(self.KEY) or {}).get("telemetry") or {})
        return {"devices_reporting": len(tele), "telemetry": tele, "mobile_arbitrary_commands": False, "mobile_spending": False, "mobile_publication": False}
