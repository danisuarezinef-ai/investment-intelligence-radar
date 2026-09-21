from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical_payload(payload: dict) -> bytes:
    unsigned = {k: v for k, v in payload.items() if k not in {"signature", "manifest_fingerprint"}}
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_private_key(args: argparse.Namespace) -> Ed25519PrivateKey:
    raw_b64 = (args.private_key_b64 or os.getenv("CEO_RELEASE_SIGNING_KEY_B64", "")).strip()
    if raw_b64:
        raw = base64.b64decode(raw_b64, validate=True)
        if len(raw) != 32:
            raise ValueError("CEO_RELEASE_SIGNING_KEY_B64 debe contener una clave Ed25519 raw de 32 bytes")
        return Ed25519PrivateKey.from_private_bytes(raw)
    if args.private_key_file:
        data = Path(args.private_key_file).read_bytes()
        try:
            key = serialization.load_pem_private_key(data, password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError("La clave PEM no es Ed25519")
            return key
        except ValueError:
            raw = base64.b64decode(data.strip(), validate=True)
            if len(raw) != 32:
                raise ValueError("El archivo de clave debe ser PEM Ed25519 o base64 raw de 32 bytes")
            return Ed25519PrivateKey.from_private_bytes(raw)
    raise ValueError("Falta clave privada: usa CEO_RELEASE_SIGNING_KEY_B64 o --private-key-file")


def main() -> int:
    ap = argparse.ArgumentParser(description="Firma un manifest de actualización CEO sin guardar la clave privada en el proyecto.")
    ap.add_argument("--draft", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--trust", default=str(Path(__file__).resolve().parents[1] / "ceo_core" / "update_trust.json"))
    ap.add_argument("--key-id", required=True)
    ap.add_argument("--private-key-b64", default="")
    ap.add_argument("--private-key-file", default="")
    ap.add_argument("--release-sequence", type=int, required=True)
    ap.add_argument("--release-id", required=True)
    ap.add_argument("--output", required=True)
    ns = ap.parse_args()

    if ns.release_sequence <= 0:
        raise ValueError("release_sequence debe ser > 0")
    package = Path(ns.package)
    if not package.is_file():
        raise FileNotFoundError(package)
    draft = json.loads(Path(ns.draft).read_text(encoding="utf-8"))
    trust = json.loads(Path(ns.trust).read_text(encoding="utf-8"))
    if not isinstance(draft, dict) or not isinstance(trust, dict):
        raise ValueError("Draft/trust inválido")

    key = load_private_key(ns)
    public_raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    trusted_b64 = str((trust.get("keys") or {}).get(ns.key_id) or "")
    if not trusted_b64:
        raise ValueError(f"key-id no existe en update_trust.json: {ns.key_id}")
    trusted_raw = base64.b64decode(trusted_b64, validate=True)
    if public_raw != trusted_raw:
        raise ValueError("La clave privada no corresponde con la clave pública confiable del paquete")

    blob = package.read_bytes()
    draft["artifact_name"] = package.name
    draft["size_bytes"] = len(blob)
    draft["sha256"] = hashlib.sha256(blob).hexdigest()
    draft["signing_key_id"] = ns.key_id
    draft["signature_alg"] = "ed25519"
    draft["release_sequence"] = ns.release_sequence
    draft["release_id"] = ns.release_id
    draft["release_status"] = "release"
    draft["manifest_fingerprint"] = hashlib.sha256(canonical_payload(draft)).hexdigest()
    draft["signature"] = base64.b64encode(key.sign(canonical_payload(draft))).decode("ascii")

    out = Path(ns.output)
    out.write_text(json.dumps(draft, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "output": str(out),
        "key_id": ns.key_id,
        "release_sequence": ns.release_sequence,
        "release_id": ns.release_id,
        "sha256": draft["sha256"],
        "size_bytes": draft["size_bytes"],
        "manifest_fingerprint": draft["manifest_fingerprint"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
