from __future__ import annotations

import argparse
import json
from pathlib import Path

from ceo_core.models import ProjectState
from ceo_core.release_qualification_v2 import ReleaseQualificationV2
from ceo_core.security_posture import SecurityPostureGate


def main() -> int:
    ap = argparse.ArgumentParser(description="CEO DEV55 fail-closed local/physical qualification aggregator")
    ap.add_argument("--root", default=".")
    ap.add_argument("--local-tests", action="store_true")
    ap.add_argument("--clean-extract-tests", action="store_true")
    ap.add_argument("--package-contract", action="store_true")
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--benchmark", action="store_true")
    ap.add_argument("--backup-restore", action="store_true")
    ap.add_argument("--field-campaign", action="store_true")
    ap.add_argument("--persistent-signer", action="store_true")
    ap.add_argument("--output")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    state = ProjectState(project_name="DEV55 qualification", goal="Qualify cumulative CEO candidate")
    security = SecurityPostureGate().assess(state, root)
    report = ReleaseQualificationV2().assess(
        state,
        local_tests_passed=args.local_tests,
        clean_extract_tests_passed=args.clean_extract_tests,
        package_contract_passed=args.package_contract,
        security_passed=security["passed"],
        stress_passed=args.stress,
        benchmark_passed=args.benchmark,
        backup_restore_passed=args.backup_restore,
        field_campaign_passed=args.field_campaign,
        signed_with_persistent_authority=args.persistent_signer,
    )
    payload = {"security": security, "qualification": report}
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["local_candidate_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
