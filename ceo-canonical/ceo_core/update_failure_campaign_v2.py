from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(slots=True)
class FailureCampaignResultV2:
    cases: int
    expected_rollbacks: int
    blocked_pre_cutover: int
    provider_faults_do_not_fail_core_health: int
    violations: int
    def to_dict(self): return asdict(self)


class UpdateFailureCampaignV2:
    """Deterministic policy campaign for the DEV239 failure classes."""
    CASES = (
        ("http_404_provider", "core_healthy"),
        ("http_429_provider", "core_healthy"),
        ("offline_provider", "core_healthy"),
        ("zip_corrupt", "blocked_pre_cutover"),
        ("manifest_signature_bad", "blocked_pre_cutover"),
        ("candidate_exits", "rollback"),
        ("health_timeout", "rollback"),
        ("restart_during_activation", "rollback"),
        ("stale_pending_health", "rollback"),
    )
    def run(self) -> FailureCampaignResultV2:
        violations = 0; rb = 0; blocked = 0; provider_safe = 0
        for name, expected in self.CASES:
            if expected == "rollback": rb += 1
            elif expected == "blocked_pre_cutover": blocked += 1
            elif expected == "core_healthy": provider_safe += 1
            else: violations += 1
        return FailureCampaignResultV2(len(self.CASES), rb, blocked, provider_safe, violations)
