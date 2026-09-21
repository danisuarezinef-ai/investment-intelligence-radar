from __future__ import annotations

import psutil


class ResourceGovernor:
    """Maps the one user-facing power slider onto CPU/RAM-aware concurrency."""

    def __init__(
        self,
        hard_worker_cap: int = 256,
        assumed_worker_ram_mb: int = 220,
        hard_cpu_safety_percent: float = 97.0,
        hard_ram_safety_percent: float = 96.0,
    ) -> None:
        self.hard_worker_cap = max(1, hard_worker_cap)
        self.assumed_worker_ram_mb = max(32, assumed_worker_ram_mb)
        self.hard_cpu_safety_percent = hard_cpu_safety_percent
        self.hard_ram_safety_percent = hard_ram_safety_percent

    def hardware_capacity(self) -> int:
        cpu = max(1, psutil.cpu_count(logical=True) or 1)
        total_mb = psutil.virtual_memory().total / (1024**2)
        # Most CEO workers are I/O-bound. CPU allows oversubscription; RAM guards browser-heavy use.
        cpu_capacity = cpu * 4
        ram_capacity = max(1, int(total_mb / self.assumed_worker_ram_mb))
        return max(1, min(self.hard_worker_cap, cpu_capacity, ram_capacity))

    def target_concurrency(self, power_percent: int) -> int:
        power = max(1, min(100, power_percent)) / 100
        target = max(1, round(self.hardware_capacity() * power))
        snap = self.snapshot()
        if snap["cpu_percent"] >= self.hard_cpu_safety_percent or snap["ram_percent"] >= self.hard_ram_safety_percent:
            target = max(1, target // 2)
        return target

    def snapshot(self) -> dict[str, float | int]:
        vm = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "logical_cpus": psutil.cpu_count(logical=True) or 1,
            "ram_percent": vm.percent,
            "ram_used_gb": round((vm.total - vm.available) / (1024**3), 2),
            "ram_available_gb": round(vm.available / (1024**3), 2),
            "ram_total_gb": round(vm.total / (1024**3), 2),
            "hardware_worker_capacity": self.hardware_capacity(),
        }

    def adaptive_target(self, power_percent: int, *, failure_rate: float = 0.0, latency_ratio: float = 1.0) -> int:
        target = self.target_concurrency(power_percent)
        # Back off under systemic failure/latency; cautiously expand when I/O-bound work is healthy.
        if failure_rate >= 0.30:
            return max(1, target // 2)
        if failure_rate >= 0.12:
            return max(1, int(target * 0.75))
        if latency_ratio > 2.0:
            return max(1, int(target * 0.8))
        return target

    def limits(self, power_percent: int) -> dict[str, int | float]:
        target = self.target_concurrency(power_percent)
        return {
            "total_workers": target,
            "browser_workers": max(1, min(target, max(1, target // 3))),
            "api_workers": target,
            "local_workers": max(1, min(target, psutil.cpu_count(logical=True) or 1)),
            "file_workers": max(1, min(target, max(2, (psutil.cpu_count(logical=True) or 1) * 2))),
            "ram_soft_percent": min(self.hard_ram_safety_percent, max(25.0, float(power_percent))),
            "cpu_soft_percent": min(self.hard_cpu_safety_percent, max(25.0, float(power_percent))),
        }
