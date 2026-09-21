from __future__ import annotations
from dataclasses import dataclass,asdict
@dataclass(slots=True)
class LongHorizonReadinessV1:
    throughput_ledger:bool; critical_path_eta:bool; wave_planner:bool; provider_fault_campaign:bool; restart_continuity:bool; adaptive_concurrency:bool; useful_milestones:bool; stall_replanner:bool; long_soak:bool; dev221_regression:bool; clean_package:bool; local_candidate_ready:bool; windows_physical_verified:bool=False; production_verified:bool=False
    def to_dict(self):return asdict(self)
def evaluate_long_horizon_readiness_v1(**gates)->LongHorizonReadinessV1:
    names=['throughput_ledger','critical_path_eta','wave_planner','provider_fault_campaign','restart_continuity','adaptive_concurrency','useful_milestones','stall_replanner','long_soak','dev221_regression','clean_package']
    vals={n:bool(gates.get(n)) for n in names}
    return LongHorizonReadinessV1(**vals,local_candidate_ready=all(vals.values()))
