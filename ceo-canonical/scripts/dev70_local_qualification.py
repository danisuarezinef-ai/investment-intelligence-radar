from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState
from ceo_core.release_readiness_v4 import ReleaseReadinessV4


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-json", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    evidence = json.loads(Path(args.evidence_json).read_text(encoding="utf-8"))
    state = ProjectState(project_name="DEV70 qualification", goal="Qualify governed mission fabric candidate")
    report = ReleaseReadinessV4().assess(
        state,
        local_tests=bool(evidence.get("local_tests")),
        clean_extract=bool(evidence.get("clean_extract")),
        package_contract=bool(evidence.get("package_contract")),
        security=bool(evidence.get("security")),
        portfolio=bool(evidence.get("portfolio")),
        quota=bool(evidence.get("quota")),
        decision_trace=bool(evidence.get("decision_trace")),
        delegation=bool(evidence.get("delegation")),
        soak=bool(evidence.get("soak")),
        freeze=bool(evidence.get("freeze")),
        persistent_signer=bool(evidence.get("persistent_signer", False)),
        windows_campaign=bool(evidence.get("windows_campaign", False)),
    )
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["local_candidate_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
