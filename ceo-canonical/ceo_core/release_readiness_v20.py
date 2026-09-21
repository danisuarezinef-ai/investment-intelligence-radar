from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass
class TerminalLocalCampaignReadinessV20:
    campaign_ticket: bool
    staleness_guard: bool
    pre_cutover_matrix: bool
    atomic_cutover: bool
    crash_recovery: bool
    dual_activation_gate: bool
    user_state_guard: bool
    exactly_once_guard: bool
    model_soak: bool
    clean_terminal_gate: bool
    windows_physical_verified: bool = False
    production_verified: bool = False
    def to_dict(self):
        local = all([self.campaign_ticket,self.staleness_guard,self.pre_cutover_matrix,self.atomic_cutover,
                     self.crash_recovery,self.dual_activation_gate,self.user_state_guard,self.exactly_once_guard,
                     self.model_soak,self.clean_terminal_gate])
        return {**asdict(self), "local_candidate_ready": local, "terminal_local_gate_passed": local,
                "next_required_evidence": "physical_windows_campaign" if local else "local_correction",
                "automatic_installation": False, "automatic_publication": False,
                "production_ready": bool(local and self.windows_physical_verified and self.production_verified)}
