from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from ceo_core.in_app_updater import InAppUpdater
from ceo_core.release_signing_authority import ReleaseSigningAuthority


def main() -> int:
    ap = argparse.ArgumentParser(description="Firma una actualización usando la autoridad persistente de Windows.")
    ap.add_argument("--draft", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--release-sequence", required=True, type=int)
    ap.add_argument("--release-id", required=True)
    ap.add_argument("--output", required=True)
    ns = ap.parse_args()
    if os.name != "nt":
        print("[BLOCKED] Este firmante usa Windows Credential Manager.")
        return 6
    if ns.release_sequence <= 0:
        raise ValueError("release_sequence debe ser > 0")
    package = Path(ns.package)
    blob = package.read_bytes()
    draft = json.loads(Path(ns.draft).read_text(encoding="utf-8"))
    draft.update({
        "artifact_name": package.name,
        "size_bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "release_sequence": ns.release_sequence,
        "release_id": ns.release_id,
        "release_status": "release",
        "signature_alg": "ed25519",
    })
    authority = ReleaseSigningAuthority()
    status = authority.status()
    if not status.configured:
        raise RuntimeError("Firmante persistente no configurado; ejecuta bootstrap_release_signer.py")
    draft["signing_key_id"] = status.key_id
    signed = authority.sign_manifest(draft)
    out = Path(ns.output)
    out.write_text(json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Independent parse/signature check through the updater using the public key only.
    verifier = InAppUpdater(trusted_keys={status.key_id: status.public_key_b64})
    verifier._manifest_from_payload(signed, require_signed=True)
    print(json.dumps({
        "ok": True,
        "output": str(out),
        "key_id": status.key_id,
        "public_fingerprint": status.public_fingerprint,
        "sha256": signed["sha256"],
        "size_bytes": signed["size_bytes"],
        "release_sequence": signed["release_sequence"],
        "release_id": signed["release_id"],
        "verified_after_signing": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
