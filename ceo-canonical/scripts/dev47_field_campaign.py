from __future__ import annotations

import argparse
import json
from pathlib import Path

from ceo_core.field_campaign import WindowsFieldCampaign
from ceo_core.models import ProjectState


def main() -> int:
    ap = argparse.ArgumentParser(description="CEO DEV47 physical Windows campaign evidence recorder")
    ap.add_argument("--state", default="DEV47_FIELD_CAMPAIGN_STATE.json")
    ap.add_argument("--candidate", default="1.3.32-rc1-governed-self-evolution")
    ap.add_argument("--record", choices=[g.gate_id for g in WindowsFieldCampaign.GATES])
    ap.add_argument("--passed", action="store_true")
    ap.add_argument("--evidence-ref")
    ap.add_argument("--detail", default="")
    args = ap.parse_args()
    path = Path(args.state)
    state = ProjectState.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else ProjectState(project_name="CEO DEV47 field campaign", goal="Validate cumulative CEO candidate on physical Windows")
    campaign = WindowsFieldCampaign()
    campaign.initialize(state, args.candidate)
    if args.record:
        if not args.evidence_ref:
            ap.error("--evidence-ref is required with --record")
        campaign.record(state, args.record, passed=args.passed, source_kind="physical_windows", evidence_ref=args.evidence_ref, detail=args.detail)
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    print(json.dumps(campaign.snapshot(state), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
