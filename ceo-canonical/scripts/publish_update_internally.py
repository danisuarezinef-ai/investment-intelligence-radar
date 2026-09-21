from __future__ import annotations

import argparse
import json
from pathlib import Path

from ceo_core.internal_release_publisher import InternalReleasePublisher


def main() -> int:
    ap = argparse.ArgumentParser(description="CEO internal no-touch release publisher")
    ap.add_argument("--package", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--release-sequence", type=int, required=True)
    ap.add_argument("--release-id", required=True)
    ap.add_argument("--notes", default="")
    ap.add_argument("--min-app-version", required=True)
    ns = ap.parse_args()
    result = InternalReleasePublisher().publish(
        package_path=Path(ns.package),
        version=ns.version,
        release_sequence=ns.release_sequence,
        release_id=ns.release_id,
        notes=ns.notes,
        min_app_version=ns.min_app_version,
    )
    print(json.dumps(result.__dict__ if hasattr(result, "__dict__") else {
        field: getattr(result, field) for field in result.__dataclass_fields__
    }, ensure_ascii=False, indent=2))
    return 0 if result.ok else 7


if __name__ == "__main__":
    raise SystemExit(main())
