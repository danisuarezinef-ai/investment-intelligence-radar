from __future__ import annotations

import argparse
import json
from pathlib import Path

from ceo_core.internal_release_coordinator import InternalReleaseCoordinator, InternalReleaseRequest


def main() -> int:
    ap=argparse.ArgumentParser(description="Internal CEO release queue entrypoint; not an operator update procedure.")
    ap.add_argument("--package",required=True)
    ap.add_argument("--version",required=True)
    ap.add_argument("--release-sequence",required=True,type=int)
    ap.add_argument("--release-id",required=True)
    ap.add_argument("--notes",default="")
    ap.add_argument("--min-app-version",required=True)
    ap.add_argument("--qualification",required=True,help="JSON qualification receipt")
    ns=ap.parse_args()
    q=json.loads(Path(ns.qualification).read_text(encoding="utf-8"))
    result=InternalReleaseCoordinator().enqueue(InternalReleaseRequest(
        package_path=ns.package,version=ns.version,release_sequence=ns.release_sequence,
        release_id=ns.release_id,notes=ns.notes,min_app_version=ns.min_app_version,
        qualification=q,
    ))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result.get("ok") else 4

if __name__=="__main__": raise SystemExit(main())
