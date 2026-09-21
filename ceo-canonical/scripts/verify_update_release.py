from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.in_app_updater import InAppUpdater


def main() -> int:
    ap = argparse.ArgumentParser(description="Verifica manifest firmado + paquete CEO antes de publicar el manifest activo.")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--current-version", default="1.3.0-rc1-updater-bootstrap")
    ns = ap.parse_args()

    payload = json.loads(Path(ns.manifest).read_text(encoding="utf-8"))
    package = Path(ns.package).resolve()
    if package.name != str(payload.get("artifact_name") or ""):
        raise ValueError("artifact_name no coincide con el paquete local")

    with tempfile.TemporaryDirectory(prefix="ceo-release-verify-") as td:
        updater = InAppUpdater(Path(td))
        manifest = updater._manifest_from_payload(payload, require_signed=True)
        compatibility = updater._compatibility_error(manifest, ns.current_version)
        if compatibility:
            raise ValueError(f"Incompatibilidad: {compatibility}")
        # Force local package transport while preserving all normal package checks.
        updater._download = lambda _m: package
        receipt = updater.stage(manifest)
        root = Path(receipt["root"])
        integrity = updater._verify_staged_integrity(root, receipt)
        print(json.dumps({
            "ok": True,
            "version": manifest.version,
            "release_sequence": manifest.release_sequence,
            "release_id": manifest.release_id,
            "contract": receipt.get("contract"),
            "staged_integrity": integrity,
            "human_confirmation_required": receipt.get("requires_human_confirmation") is True,
            "automatic_promotion": receipt.get("automatic_promotion"),
        }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
