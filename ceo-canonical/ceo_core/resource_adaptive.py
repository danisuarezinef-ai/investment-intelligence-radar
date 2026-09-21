from __future__ import annotations

from dataclasses import dataclass, asdict
from statistics import median
from time import perf_counter
import subprocess

import psutil

from .models import ProjectState
from .resource_governor import ResourceGovernor




class GPUProbe:
    """Best-effort GPU/VRAM discovery without a hard dependency on vendor SDKs."""
    def snapshot(self)->dict:
        try:
            proc=subprocess.run(["nvidia-smi","--query-gpu=name,memory.total,memory.used,utilization.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=2)
            if proc.returncode!=0:return {"available":False,"devices":[]}
            devices=[]
            for line in proc.stdout.strip().splitlines():
                parts=[x.strip() for x in line.split(',')]
                if len(parts)>=4:devices.append({"name":parts[0],"vram_total_mb":float(parts[1]),"vram_used_mb":float(parts[2]),"utilization_percent":float(parts[3])})
            return {"available":bool(devices),"devices":devices}
        except Exception:
            return {"available":False,"devices":[]}


@dataclass(slots=True)
class CapacityProfile:
    logical_cpus: int
    ram_total_gb: float
    base_worker_capacity: int
    browser_safe_workers: int
    samples: dict[str, dict]


class CapacityProfiler:
    """Produces a hardware profile and learns safe concurrency from observed samples."""

    def __init__(self, governor: ResourceGovernor | None = None) -> None:
        self.governor = governor or ResourceGovernor()
        self.gpu = GPUProbe()

    def profile(self, state: ProjectState | None = None) -> CapacityProfile:
        snap = self.governor.snapshot()
        total_gb = float(snap["ram_total_gb"])
        base = int(snap["hardware_worker_capacity"])
        browser_safe = max(1, min(base, int((total_gb * 1024 * .70) / 240)))
        samples = dict((state.metadata.get("capacity_samples", {}) if state else {}))
        out = CapacityProfile(int(snap["logical_cpus"]), total_gb, base, browser_safe, samples)
        if state is not None:
            state.metadata["capacity_profile"] = asdict(out)
        return out

    def record(self, state: ProjectState, power: int, *, workers: int, throughput: float, ram_percent: float, cpu_percent: float, failures: float = 0.0) -> None:
        rows = state.metadata.setdefault("capacity_samples", {}).setdefault(str(power), [])
        rows.append({"workers": workers, "throughput": throughput, "ram_percent": ram_percent, "cpu_percent": cpu_percent, "failures": failures})
        del rows[:-50]

    def scenario(self, state: ProjectState, power: int) -> dict:
        rows = list(state.metadata.get("capacity_samples", {}).get(str(power), []))
        if rows:
            healthy = [r for r in rows if float(r.get("failures", 0)) < .15] or rows
            best = max(healthy, key=lambda r: float(r.get("throughput", 0)))
            return {"power": power, "workers": int(best["workers"]), "throughput": float(best["throughput"]), "observed": True}
        workers = self.governor.target_concurrency(power)
        return {"power": power, "workers": workers, "throughput": 0.0, "observed": False}


class AdaptiveResourceGovernor:
    """Maps the single UI power control to resource classes and learned capacity."""

    def __init__(self, governor: ResourceGovernor | None = None) -> None:
        self.governor = governor or ResourceGovernor()
        self.profiler = CapacityProfiler(self.governor)
        self.gpu = GPUProbe()

    def plan(self, state: ProjectState) -> dict:
        limits = self.governor.limits(state.power_percent)
        cap = self.profiler.profile(state)
        browser = min(int(limits["browser_workers"]), cap.browser_safe_workers)
        gpu = self.gpu.snapshot()
        plan = {**limits, "browser_workers": browser, "power_percent": state.power_percent, "gpu": gpu}
        if gpu.get("available"):
            free_vram=sum(max(0.0,float(d.get("vram_total_mb",0))-float(d.get("vram_used_mb",0))) for d in gpu.get("devices",[]))
            plan["gpu_workers"] = max(1, min(int(limits.get("local_workers",1)), int(free_vram//2048) or 1))
        else:
            plan["gpu_workers"] = 0
        state.metadata["resource_plan"] = plan
        return plan
