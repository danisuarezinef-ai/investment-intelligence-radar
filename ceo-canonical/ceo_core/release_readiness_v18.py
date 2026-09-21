from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(slots=True)
class OneShotCampaignReadinessV18:
    dev242_baseline_snapshot: bool
    dev243_candidate_identity_lock: bool
    dev244_campaign_checkpoint: bool
    dev245_recovery_point: bool
    dev246_startup_watchdog: bool
    dev247_root_cause_triage: bool
    dev248_productive_smoke: bool
    dev249_one_shot_executor: bool
    dev250_campaign_soak: bool
    dev251_clean_package_gate: bool
    windows_physical_verified: bool = False
    production_verified: bool = False

    @property
    def local_candidate_ready(self) -> bool:
        return all((self.dev242_baseline_snapshot, self.dev243_candidate_identity_lock, self.dev244_campaign_checkpoint,
                    self.dev245_recovery_point, self.dev246_startup_watchdog, self.dev247_root_cause_triage,
                    self.dev248_productive_smoke, self.dev249_one_shot_executor, self.dev250_campaign_soak,
                    self.dev251_clean_package_gate))

    def to_dict(self):
        row = asdict(self); row["local_candidate_ready"] = self.local_candidate_ready; return row
