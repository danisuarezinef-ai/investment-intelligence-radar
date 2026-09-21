from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from .campaign_baseline_snapshot_v2 import CampaignBaselineSnapshotV2
from .campaign_checkpoint_v2 import CampaignCheckpointV2
from .candidate_identity_lock_v1 import CandidateIdentityLockV1
from .pre_cutover_recovery_point_v1 import PreCutoverRecoveryPointV1


class OneShotWindowsCampaignExecutorV1:
    """Prepares and checks a one-shot campaign. Cutover is impossible without explicit confirmation."""

    def __init__(self, *, updates_root: str | Path, package_path: str | Path, version: str):
        self.root = Path(updates_root)
        self.package = Path(package_path)
        self.version = str(version)
        raw = f"{self.version}:{self.package.name}:{self.package.stat().st_size if self.package.exists() else 0}"
        self.campaign_id = hashlib.sha256(raw.encode()).hexdigest()[:20]
        self.work = self.root / "campaigns" / self.campaign_id
        self.checkpoint = CampaignCheckpointV2(self.work / "checkpoint.json", campaign_id=self.campaign_id)
        self.identity = CandidateIdentityLockV1(self.work / "candidate-lock.json")

    def prepare(self) -> dict[str, Any]:
        baseline = CampaignBaselineSnapshotV2(self.root).capture()
        self.checkpoint.record("baseline", evidence={"snapshot_sha256": baseline["snapshot_sha256"]})
        lock = self.identity.create(package_path=self.package, version=self.version, campaign_id=self.campaign_id)
        self.checkpoint.record("identity_lock", evidence={"sha256": lock["sha256"]})
        recovery = PreCutoverRecoveryPointV1(self.root).create(campaign_id=self.campaign_id)
        if not recovery.get("restorable"):
            raise RuntimeError("campaign has no restorable current pointer")
        self.checkpoint.record("recovery_point", evidence={"path": recovery["path"]})
        return {
            "campaign_id": self.campaign_id,
            "baseline": baseline,
            "identity_lock": lock,
            "recovery_point": recovery,
            "ready_for_stage": True,
            "cutover_authorized": False,
            "automatic_installation": False,
        }

    def authorize_cutover(self, *, confirmation: str) -> dict[str, Any]:
        expected = f"ACTIVATE {self.campaign_id} {self.identity.verify(self.package, expected_version=self.version, campaign_id=self.campaign_id).get('lock',{}).get('sha256','')}"
        ok = str(confirmation).strip() == expected
        return {"authorized": ok, "campaign_id": self.campaign_id, "expected_confirmation": expected if not ok else None,
                "side_effects_allowed": ok, "explicit_human_confirmation_required": True}

    def snapshot(self) -> dict[str, Any]:
        return {"campaign_id": self.campaign_id, "version": self.version, "checkpoint": self.checkpoint.resumable_state(),
                "identity": self.identity.verify(self.package, expected_version=self.version, campaign_id=self.campaign_id),
                "automatic_installation": False}
