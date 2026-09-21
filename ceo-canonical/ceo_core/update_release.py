from __future__ import annotations

import base64
import hashlib
import json
import os
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .in_app_updater import InAppUpdater




def _norm(rel: str) -> str:
    p = PurePosixPath(str(rel).replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unsafe release path: {rel}")
    return str(p)


def build_package_contract(
    source_root: str | Path,
    *,
    app_version: str,
    launcher: str = "ABRIR_CEO.cmd",
    data_schema_version: int = 1,
    required_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    root = Path(source_root)
    default_required = (launcher, InAppUpdater.PACKAGE_CONTRACT_NAME, *InAppUpdater.REQUIRED_RUNTIME_PATHS)
    required = list(dict.fromkeys(_norm(x) for x in (required_paths or default_required)))
    if InAppUpdater.PACKAGE_CONTRACT_NAME not in required:
        required.append(InAppUpdater.PACKAGE_CONTRACT_NAME)
    # The contract cannot hash itself before it exists. Its self-hash uses the
    # canonical contract with an empty self slot, then is written as the final slot.
    hashes: dict[str, str] = {}
    for rel in required:
        if rel == InAppUpdater.PACKAGE_CONTRACT_NAME:
            continue
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"required release file missing: {rel}")
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    contract = {
        "contract_version": InAppUpdater.SUPPORTED_PACKAGE_CONTRACT_VERSION,
        "app_version": str(app_version),
        "data_schema_version": int(data_schema_version),
        "launcher": _norm(launcher),
        "required_paths": required,
        "file_hashes": hashes,
    }
    return contract


def write_package_contract(source_root: str | Path, **kwargs: Any) -> Path:
    root = Path(source_root)
    contract = build_package_contract(root, **kwargs)
    path = root / InAppUpdater.PACKAGE_CONTRACT_NAME
    path.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def sign_manifest_payload(payload: dict[str, Any], *, private_key_b64: str, key_id: str) -> dict[str, Any]:
    row = dict(payload)
    row["signature_alg"] = "ed25519"
    row["signing_key_id"] = str(key_id)
    row.pop("signature", None)
    row.pop("manifest_fingerprint", None)
    private_raw = base64.b64decode(private_key_b64.strip(), validate=True)
    key = Ed25519PrivateKey.from_private_bytes(private_raw)
    row["manifest_fingerprint"] = InAppUpdater.manifest_fingerprint(row)
    row["signature"] = base64.b64encode(key.sign(InAppUpdater._signed_payload_bytes(row))).decode("ascii")
    return row


def _release_members(root: Path) -> list[Path]:
    """Return the production payload only; historical launchers/tests/reports stay out."""
    exact_root = {
        "ABRIR_CEO.cmd",
        "pyproject.toml",
        "CEO_UPDATE_PACKAGE.json",
        "RC1_FREEZE_POLICY.json",
    }
    dirs = {"ceo_core", "scripts", "schemas", "ceo_app", "assets", "runtime"}
    members: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if any(part in {"__pycache__", ".pytest_cache", ".git"} for part in parts):
            continue
        if rel.as_posix() in exact_root or (parts and parts[0] in dirs):
            low = rel.as_posix().lower()
            if low.endswith((".pyc", ".pyo", ".part")):
                continue
            if "private.key" in low or "release_secrets" in low or "release-private" in low:
                continue
            # Only the canonical launcher is distributable.  Scripts named
            # ABRIR_/VALIDAR_ are historical developer tooling, not user entrypoints.
            if path.name.upper().startswith(("ABRIR_CEO_", "VALIDAR_", "REANUDAR_")):
                continue
            members.append(path)
    return sorted(set(members))


def build_update_zip(
    source_root: str | Path,
    output_path: str | Path,
    *,
    app_version: str,
    launcher: str = "ABRIR_CEO.cmd",
    data_schema_version: int = 1,
) -> Path:
    root = Path(source_root)
    contract_path = write_package_contract(
        root,
        app_version=app_version,
        launcher=launcher,
        data_schema_version=data_schema_version,
    )
    _ = contract_path
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in _release_members(root):
            zf.write(path, arcname=path.relative_to(root).as_posix())
    return output


def private_key_from_environment_or_file(path: str | Path | None = None) -> str:
    env = os.getenv("CEO_UPDATE_SIGNING_KEY_B64", "").strip()
    if env:
        return env
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    raise RuntimeError("No release signing private key configured")
