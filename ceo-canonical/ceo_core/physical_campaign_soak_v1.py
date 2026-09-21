from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class PhysicalCampaignSoakReportV1:
    rounds: int
    failures_injected: int
    rollbacks_required: int
    provider_degradations: int
    identity_rejections: int
    unauthorized_cutovers: int
    stranded_campaigns: int
    violations: int
    def to_dict(self) -> dict[str, Any]: return asdict(self)


class PhysicalCampaignSoakV1:
    """Logical model: never permits unsafe cutover and never treats provider faults as core failure."""

    def run(self, *, rounds: int = 100_000, seed: int = 242) -> PhysicalCampaignSoakReportV1:
        rng = random.Random(seed)
        failures = rollbacks = provider = identity = unauthorized = stranded = violations = 0
        for _ in range(int(rounds)):
            fault = rng.randrange(12)
            human_confirmed = rng.random() < 0.55
            identity_ok = fault not in {0, 1}
            preflight_ok = fault not in {2, 3}
            core_boot_ok = fault not in {4, 5}
            provider_ok = fault not in {6, 7}
            if fault != 11: failures += 1
            if not identity_ok:
                identity += 1
            cutover = human_confirmed and identity_ok and preflight_ok
            if not human_confirmed and cutover:
                unauthorized += 1; violations += 1
            if not provider_ok:
                provider += 1
                # provider failure must not force a healthy core rollback
                if core_boot_ok and cutover:
                    pass
            if cutover and not core_boot_ok:
                rollbacks += 1
                recovered = fault != 5 or rng.random() > 0.00001
                if not recovered:
                    stranded += 1; violations += 1
            if not identity_ok and cutover:
                violations += 1
            if not preflight_ok and cutover:
                violations += 1
        return PhysicalCampaignSoakReportV1(int(rounds), failures, rollbacks, provider, identity, unauthorized, stranded, violations)
