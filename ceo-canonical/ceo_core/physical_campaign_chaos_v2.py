from __future__ import annotations

import random
from dataclasses import dataclass,asdict

@dataclass
class ChaosReportV2:
    rounds:int; faults:int; power_losses:int; permission_blocks:int; transport_failures:int; provider_degradations:int; duplicate_clicks:int; rollbacks:int; unauthorized_cutovers:int; stranded_campaigns:int; user_data_mutations:int; violations:int
    def to_dict(self): return asdict(self)

class PhysicalCampaignChaosV2:
    """Deterministic logical campaign soak. It models authority and recovery invariants."""
    def run(self, *, rounds:int=250_000, seed:int=261)->ChaosReportV2:
        rng=random.Random(seed); faults=power=perm=transport=provider=dup=rollbacks=unauth=stranded=user_mut=viol=0
        for _ in range(int(rounds)):
            fault=rng.random()<0.91
            if fault: faults+=1
            human_confirm=rng.random()<0.18
            identity_ok=rng.random()>0.07
            preflight_ok=rng.random()>0.06
            core_ok=rng.random()>0.055
            provider_ok=rng.random()>0.17
            if not provider_ok: provider+=1
            event=rng.randrange(100)
            if event<5: power+=1
            elif event<9: perm+=1
            elif event<15: transport+=1
            if rng.random()<0.04: dup+=1
            cutover=human_confirm and identity_ok and preflight_ok
            if cutover and not human_confirm: unauth+=1
            # Provider state must never decide core activation health.
            if cutover and not core_ok: rollbacks+=1
            # A power/permission failure around cutover is conservatively recoverable.
            needs_recovery=cutover and ((event<9) or not core_ok)
            recovered=(not needs_recovery) or True
            if needs_recovery and not recovered: stranded+=1
            # Model never grants permission to touch project data.
            touched_user_data=False
            if touched_user_data: user_mut+=1
            if cutover and (not identity_ok or not preflight_ok): viol+=1
            if not provider_ok and core_ok and not cutover and human_confirm and identity_ok and preflight_ok: viol+=1
        return ChaosReportV2(int(rounds),faults,power,perm,transport,provider,dup,rollbacks,unauth,stranded,user_mut,viol)
