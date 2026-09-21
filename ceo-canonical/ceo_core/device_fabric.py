from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Iterable

from .models import ProjectState, Task, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class DeviceProfile:
    device_id: str
    kind: str  # windows | mobile | other
    online: bool = True
    capabilities: tuple[str, ...] = ()
    ram_gb: float = 0.0
    performance_score: float = 0.5
    efficiency_score: float = 0.5
    thermal_headroom: float = 1.0
    battery_percent: float | None = None
    network_score: float = 1.0
    notification_sink: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveDeviceFabric:
    """Device-aware task placement for the future Windows + phone CEO fabric.

    This is deliberately transport-agnostic: it decides *where* a task belongs, while
    the existing provider/application routers decide *how* that device executes it.
    A running task may be marked for migration when user power settings change, but it
    is only safe to pre-empt when a remote execution transport is actually connected.
    """

    KEY = "device_fabric_v1"
    WINDOWS_ONLY = {"windows_ui", "desktop", "native_app", "powershell", "cmd", "windows_install", "vscode"}

    def initialize_windows(self, state: ProjectState, *, ram_gb: float = 0.0, performance_score: float = 0.65) -> dict[str, Any]:
        meta = state.metadata.setdefault(self.KEY, {})
        devices = meta.setdefault("devices", {})
        devices.setdefault("windows-primary", DeviceProfile(
            device_id="windows-primary",
            kind="windows",
            online=True,
            capabilities=("windows", "filesystem", "terminal", "browser", "desktop", "git_local"),
            ram_gb=float(ram_gb or 0.0),
            performance_score=float(performance_score),
            efficiency_score=0.45,
            thermal_headroom=1.0,
            battery_percent=None,
            network_score=1.0,
            notification_sink=False,
        ).to_dict())
        meta.setdefault("notification_policy", {"decision_notifications_prefer": "mobile"})
        meta.setdefault("migration_threshold", 0.12)
        meta["updated_at"] = _now()
        return meta

    def register(self, state: ProjectState, profile: DeviceProfile) -> None:
        meta = state.metadata.setdefault(self.KEY, {})
        meta.setdefault("devices", {})[profile.device_id] = profile.to_dict()
        meta["updated_at"] = _now()

    def profiles(self, state: ProjectState) -> list[DeviceProfile]:
        rows = (state.metadata.get(self.KEY) or {}).get("devices") or {}
        out: list[DeviceProfile] = []
        for raw in rows.values():
            try:
                caps = tuple(str(x) for x in (raw.get("capabilities") or ()))
                out.append(DeviceProfile(
                    device_id=str(raw.get("device_id")), kind=str(raw.get("kind") or "other"),
                    online=bool(raw.get("online", True)), capabilities=caps,
                    ram_gb=float(raw.get("ram_gb", 0.0) or 0.0),
                    performance_score=float(raw.get("performance_score", 0.5) or 0.5),
                    efficiency_score=float(raw.get("efficiency_score", 0.5) or 0.5),
                    thermal_headroom=float(raw.get("thermal_headroom", 1.0) or 1.0),
                    battery_percent=(None if raw.get("battery_percent") is None else float(raw.get("battery_percent"))),
                    network_score=float(raw.get("network_score", 1.0) or 1.0),
                    notification_sink=bool(raw.get("notification_sink", False)),
                ))
            except Exception:
                continue
        return out

    @staticmethod
    def _task_kind(task: Task) -> str:
        return str(task.metadata.get("task_kind") or task.metadata.get("preferred_device_kind") or "general").lower()

    def _eligible(self, task: Task, device: DeviceProfile) -> bool:
        if not device.online:
            return False
        kind = self._task_kind(task)
        required = {str(x).lower() for x in task.required_capabilities}
        if kind in self.WINDOWS_ONLY or required.intersection(self.WINDOWS_ONLY):
            return device.kind == "windows"
        required_device_caps = set(str(x).lower() for x in (task.metadata.get("required_device_capabilities") or []))
        if required_device_caps and not required_device_caps.issubset({x.lower() for x in device.capabilities}):
            return False
        need_ram = float(task.metadata.get("estimated_ram_gb", 0.0) or 0.0)
        if need_ram > 0 and device.ram_gb > 0 and device.ram_gb < need_ram:
            return False
        return True

    def score(self, task: Task, device: DeviceProfile, power_percent: int) -> float:
        if not self._eligible(task, device):
            return float("-inf")
        p = max(1, min(100, int(power_percent))) / 100.0
        perf_weight = 0.25 + 0.60 * p
        eff_weight = 0.55 * (1.0 - p)
        thermal_weight = 0.15
        network_weight = 0.10
        ram_bonus = min(0.20, max(0.0, device.ram_gb - float(task.metadata.get("estimated_ram_gb", 0.0) or 0.0)) / 64.0)
        kind = self._task_kind(task)
        affinity = 0.0
        if kind in {"local_model", "embedding", "batch_tests", "code_review", "summarize", "research", "reasoning"} and device.kind == "mobile":
            affinity += 0.08
        if kind in self.WINDOWS_ONLY and device.kind == "windows":
            affinity += 0.40
        battery_penalty = 0.0
        if device.battery_percent is not None and device.battery_percent < 20:
            battery_penalty = (20 - device.battery_percent) / 100.0
        return (
            perf_weight * device.performance_score
            + eff_weight * device.efficiency_score
            + thermal_weight * device.thermal_headroom
            + network_weight * device.network_score
            + ram_bonus + affinity - battery_penalty
        )

    def choose(self, state: ProjectState, task: Task, *, power_percent: int | None = None) -> dict[str, Any]:
        self.initialize_windows(state)
        power = int(power_percent if power_percent is not None else state.power_percent)
        scored = []
        for device in self.profiles(state):
            score = self.score(task, device, power)
            if score != float("-inf"):
                scored.append((score, device))
        if not scored:
            return {"device_id": None, "kind": None, "score": None, "reason": "no_eligible_device", "power_percent": power}
        scored.sort(key=lambda x: x[0], reverse=True)
        score, device = scored[0]
        return {
            "device_id": device.device_id,
            "kind": device.kind,
            "score": round(score, 4),
            "reason": "highest_capability_score_for_current_power",
            "power_percent": power,
        }

    def rebalance(self, state: ProjectState) -> dict[str, Any]:
        self.initialize_windows(state)
        threshold = float((state.metadata.get(self.KEY) or {}).get("migration_threshold", 0.12) or 0.12)
        changes = []
        migrations = []
        for task in state.leaf_tasks:
            if task.status in {TaskStatus.COMPLETE, TaskStatus.SUPERSEDED, TaskStatus.FAILED}:
                continue
            choice = self.choose(state, task)
            previous = task.metadata.get("selected_device")
            if choice.get("device_id") and previous != choice["device_id"]:
                task.metadata["selected_device"] = choice["device_id"]
                task.metadata["selected_device_kind"] = choice["kind"]
                task.metadata["device_score"] = choice["score"]
                changes.append({"task_id": task.id, "from": previous, "to": choice["device_id"], "status": task.status.value})
                if task.status == TaskStatus.RUNNING and previous:
                    # Do not kill work unless the transport declares it checkpointable.
                    if bool(task.metadata.get("preemptible", False)) and bool(task.metadata.get("checkpointable", False)):
                        task.metadata["device_migration_requested"] = {
                            "from": previous, "to": choice["device_id"], "requested_at": _now(),
                            "reason": "power_or_capability_rebalance",
                        }
                        migrations.append(task.id)
        meta = state.metadata.setdefault(self.KEY, {})
        meta["last_rebalance"] = {"ts": _now(), "power_percent": state.power_percent, "changes": changes, "migration_requests": migrations}
        return {"changes": changes, "migration_requests": migrations, "devices": [p.to_dict() for p in self.profiles(state)]}

    def notification_target(self, state: ProjectState) -> dict[str, Any]:
        mobiles = [p for p in self.profiles(state) if p.online and p.kind == "mobile" and p.notification_sink]
        if mobiles:
            best = max(mobiles, key=lambda p: p.network_score)
            return {"device_id": best.device_id, "kind": "mobile", "pinned": True}
        return {"device_id": None, "kind": "mobile", "pinned": True, "status": "awaiting_mobile_node"}
