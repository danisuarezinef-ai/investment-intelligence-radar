from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ceo_core.release_signing_authority import ReleaseSigningAuthority
from ceo_core.runtime import user_data_root
from ceo_core.in_app_updater import InAppUpdater


def main() -> int:
    ap = argparse.ArgumentParser(description="Inicializa o comprueba el firmante persistente de releases de CEO.")
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--confirm-rotation", action="store_true")
    ns = ap.parse_args()
    if os.name != "nt":
        print("[BLOCKED] El firmante persistente se inicializa únicamente en Windows.")
        return 6
    authority = ReleaseSigningAuthority()
    if ns.rotate:
        status = authority.rotate_key(confirmed=ns.confirm_rotation)
    else:
        status = authority.ensure_key()
    receipt = user_data_root() / "updates" / "release-signer.json"
    authority.write_public_receipt(receipt)
    updater = InAppUpdater()
    if status.key_id not in updater._trusted_keys:
        raise RuntimeError("El actualizador no reconoce la clave pública del firmante local")
    result = {
        "ok": True,
        "configured": status.configured,
        "key_id": status.key_id,
        "public_fingerprint": status.public_fingerprint,
        "storage": status.storage,
        "self_test": status.self_test,
        "receipt": str(receipt),
        "private_key_exported": False,
        "updater_trusts_local_signer": True,
        "windows_physical_verified": True,
    }
    field = user_data_root() / "updates" / "release-signer-field.json"
    field.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["field_evidence"] = str(field)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
