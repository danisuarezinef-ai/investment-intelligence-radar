from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = "danisuarezinef-ai/investment-intelligence-radar"
BRANCH = "ceo-update-channel"
PREFIX = "ceo-updates/"
VERSION = "1.5.78-rc1-reliable-update-handoff"
RELEASE_SEQUENCE = 302
RELEASE_ID = "dev302-1.5.78-rc1-reliable-update-handoff"
PACKAGE_NAME = "CEO_1.5.78-rc1-reliable-update-handoff.zip"
PACKAGE_SIZE = 1136520
PACKAGE_SHA256 = "4b7fa43511c824e5fa45039480721f604b1e5ef520cfda86a7a9d1f25c02ddbc"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{PREFIX}"
DRAFT_URL = RAW_BASE + "DEV302_MANIFEST_UNSIGNED.json"
PACKAGE_URL = RAW_BASE + PACKAGE_NAME
MANIFEST_URL = RAW_BASE + "manifest.json"
CURRENT_EXPECTED = "1.5.58-rc1-productive-stall-escape"


def user_data_root() -> Path:
    return Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "CEO de IAs"


def outbox_file() -> Path:
    p = user_data_root() / "updates" / "outbox" / "DEV302_MANIFEST_SIGNED.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def status_file() -> Path:
    p = user_data_root() / "updates" / "bridge" / "DEV302_TRANSITION_STATUS.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_status(payload: dict) -> None:
    row = dict(payload)
    row.setdefault("generated_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    path = status_file()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def fail(status: str, detail: str = "", code: int = 2) -> int:
    payload = {
        "ok": False,
        "status": status,
        "detail": detail[:2500],
        "signed_manifest": str(outbox_file()) if outbox_file().exists() else "",
        "private_key_exported": False,
        "key_rotated": False,
        "installed": False,
    }
    try:
        write_status(payload)
    except Exception:
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def fetch_bytes(url: str, timeout: int = 120) -> bytes:
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        url + sep + f"ceo_transition={int(time.time())}",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
            "User-Agent": "CEO-de-IAs-DEV302-transition",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def installed_root() -> Path:
    pointer = user_data_root() / "updates" / "current.json"
    if pointer.is_file():
        row = json.loads(pointer.read_text(encoding="utf-8"))
        root = Path(str(row.get("root") or "")).expanduser()
        if (root / "ceo_core" / "release_signing_authority.py").is_file():
            return root.resolve()
    fallback = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "Programs" / "CEO de IAs"
    if (fallback / "ceo_core" / "release_signing_authority.py").is_file():
        return fallback.resolve()
    raise RuntimeError("CEO_INSTALL_ROOT_NOT_FOUND")


def active_version() -> str:
    pointer = user_data_root() / "updates" / "current.json"
    if not pointer.is_file():
        return ""
    try:
        return str(json.loads(pointer.read_text(encoding="utf-8")).get("version") or "")
    except Exception:
        return ""


def verify_package_contract(package: Path) -> dict:
    if package.stat().st_size != PACKAGE_SIZE:
        raise RuntimeError(f"PACKAGE_SIZE_MISMATCH:{package.stat().st_size}")
    got = sha256_file(package)
    if got != PACKAGE_SHA256:
        raise RuntimeError(f"PACKAGE_SHA256_MISMATCH:{got}")
    with zipfile.ZipFile(package, "r") as zf:
        if zf.testzip() is not None:
            raise RuntimeError("PACKAGE_ZIP_CRC_FAILED")
        names = set(zf.namelist())
        if "CEO_UPDATE_PACKAGE.json" not in names:
            raise RuntimeError("PACKAGE_CONTRACT_MISSING")
        contract = json.loads(zf.read("CEO_UPDATE_PACKAGE.json").decode("utf-8"))
        if str(contract.get("app_version") or "") != VERSION:
            raise RuntimeError("PACKAGE_VERSION_MISMATCH")
        required = [str(x) for x in contract.get("required_paths") or []]
        if names != set(required):
            raise RuntimeError("PACKAGE_DECLARED_PATH_SET_MISMATCH")
        for rel, expected in (contract.get("file_hashes") or {}).items():
            actual = hashlib.sha256(zf.read(rel)).hexdigest()
            if actual != str(expected):
                raise RuntimeError(f"PACKAGE_HASH_MISMATCH:{rel}")
        return contract


def run_git(args: list[str], cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


def publish_signed_manifest(signed: dict, verifier) -> tuple[bool, str]:
    if shutil.which("git") is None:
        return False, "GIT_NOT_AVAILABLE"
    with tempfile.TemporaryDirectory(prefix="ceo-dev302-publish-") as td:
        repo = Path(td) / "repo"
        cp = run_git([
            "clone", "--depth", "1", "--single-branch", "--branch", BRANCH,
            f"https://github.com/{REPO}.git", str(repo),
        ])
        if cp.returncode != 0:
            return False, "GIT_CLONE_FAILED:" + (cp.stderr or cp.stdout)[-1000:]

        updates = repo / "ceo-updates"
        pkg = updates / PACKAGE_NAME
        if not pkg.is_file():
            return False, "REMOTE_STAGED_PACKAGE_MISSING"
        if pkg.stat().st_size != PACKAGE_SIZE or sha256_file(pkg) != PACKAGE_SHA256:
            return False, "REMOTE_STAGED_PACKAGE_MISMATCH"

        current = updates / "manifest.json"
        if current.is_file():
            row = json.loads(current.read_text(encoding="utf-8"))
            seq = int(row.get("release_sequence") or 0)
            if seq > RELEASE_SEQUENCE:
                return False, f"REMOTE_SEQUENCE_AHEAD:{seq}"
            if seq == RELEASE_SEQUENCE:
                verifier._manifest_from_payload(row, require_signed=True)
                if str(row.get("release_id") or "") == RELEASE_ID:
                    return True, "ALREADY_PUBLISHED"
                return False, "REMOTE_SEQUENCE_COLLISION"

        signed_text = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        (updates / "DEV302_MANIFEST_SIGNED.json").write_text(signed_text, encoding="utf-8")
        current.write_text(signed_text, encoding="utf-8")

        for args in (["config", "user.name", "CEO de IAs"], ["config", "user.email", "ceo-local@localhost"]):
            cp = run_git(list(args), cwd=repo)
            if cp.returncode != 0:
                return False, "GIT_CONFIG_FAILED:" + (cp.stderr or cp.stdout)[-1000:]
        cp = run_git(["add", "ceo-updates/manifest.json", "ceo-updates/DEV302_MANIFEST_SIGNED.json"], cwd=repo)
        if cp.returncode != 0:
            return False, "GIT_STAGE_FAILED:" + (cp.stderr or cp.stdout)[-1000:]
        cp = run_git(["commit", "-m", "Activate signed DEV302 final major update"], cwd=repo)
        if cp.returncode not in (0, 1):
            return False, "GIT_COMMIT_FAILED:" + (cp.stderr or cp.stdout)[-1000:]
        cp = run_git(["push", "origin", BRANCH], cwd=repo)
        if cp.returncode != 0:
            return False, "GIT_PUSH_AUTH_REQUIRED:" + (cp.stderr or cp.stdout)[-1200:]

    remote = json.loads(fetch_bytes(MANIFEST_URL, 30).decode("utf-8"))
    verifier._manifest_from_payload(remote, require_signed=True)
    if str(remote.get("version") or "") != VERSION:
        return False, "REMOTE_VERIFY_WRONG_VERSION"
    if int(remote.get("release_sequence") or 0) != RELEASE_SEQUENCE:
        return False, "REMOTE_VERIFY_WRONG_SEQUENCE"
    if str(remote.get("sha256") or "") != PACKAGE_SHA256:
        return False, "REMOTE_VERIFY_WRONG_PACKAGE_HASH"
    return True, "PUBLISHED_AND_VERIFIED"


def install_resilient_atomic_writer(InAppUpdater) -> None:
    original = InAppUpdater._atomic_json

    def resilient(path: Path, payload: dict) -> None:
        last: PermissionError | None = None
        for attempt in range(40):
            try:
                return original(path, payload)
            except PermissionError as exc:
                last = exc
                try:
                    p = Path(path)
                    if p.exists():
                        os.chmod(p, stat.S_IREAD | stat.S_IWRITE)
                except OSError:
                    pass
                if attempt >= 39:
                    raise
                time.sleep(min(0.25, 0.025 * (attempt + 1)))
        if last is not None:
            raise last

    InAppUpdater._atomic_json = staticmethod(resilient)


def stage_candidate(InAppUpdater, signed: dict, signer) -> dict:
    install_resilient_atomic_writer(InAppUpdater)
    updater = InAppUpdater(trusted_keys={signer.key_id: signer.public_key_b64})
    manifest = updater._manifest_from_payload(signed, require_signed=True)
    if str(manifest.version) != VERSION or str(manifest.sha256) != PACKAGE_SHA256:
        raise RuntimeError("SIGNED_MANIFEST_IDENTITY_MISMATCH")
    row = updater.stage(manifest)
    progress = updater.progress()
    if str(row.get("version") or "") != VERSION:
        raise RuntimeError("STAGED_WRONG_VERSION")
    if not row.get("contract_verified"):
        raise RuntimeError("STAGED_CONTRACT_NOT_VERIFIED")
    if str(progress.get("phase") or "") != "ready_to_install":
        raise RuntimeError("STAGING_DID_NOT_REACH_READY_TO_INSTALL")
    return {
        "version": row.get("version"),
        "contract_verified": bool(row.get("contract_verified")),
        "file_count": int(row.get("file_count") or 0),
        "phase": progress.get("phase"),
        "percent": progress.get("percent"),
        "root": row.get("root"),
    }


def main() -> int:
    if os.name != "nt":
        return fail("WINDOWS_REQUIRED", "Este puente debe ejecutarse en el Windows donde está instalado CEO.", 6)

    try:
        current = active_version()
        if current and current != CURRENT_EXPECTED:
            if current == VERSION:
                return fail("ALREADY_ON_DEV302", "CEO ya está en 1.5.78; no hace falta repetir la transición.", 0)
            return fail("UNEXPECTED_ACTIVE_VERSION", f"Versión activa detectada: {current}", 7)

        root = installed_root()
        sys.path.insert(0, str(root))
        from ceo_core.release_signing_authority import ReleaseSigningAuthority
        from ceo_core.in_app_updater import InAppUpdater

        draft = json.loads(fetch_bytes(DRAFT_URL, 30).decode("utf-8"))
        exact = {
            "version": VERSION,
            "release_sequence": RELEASE_SEQUENCE,
            "release_id": RELEASE_ID,
            "artifact_name": PACKAGE_NAME,
            "size_bytes": PACKAGE_SIZE,
            "sha256": PACKAGE_SHA256,
            "url": PACKAGE_URL,
            "min_app_version": CURRENT_EXPECTED,
        }
        for key, expected in exact.items():
            if draft.get(key) != expected:
                return fail("PREPARED_MANIFEST_MISMATCH", f"{key}: {draft.get(key)!r} != {expected!r}", 8)

        with tempfile.TemporaryDirectory(prefix="ceo-dev302-transition-") as td:
            package = Path(td) / PACKAGE_NAME
            package.write_bytes(fetch_bytes(PACKAGE_URL, 180))
            verify_package_contract(package)

        authority = ReleaseSigningAuthority()
        signer = authority.status()
        if not signer.configured or not signer.self_test:
            return fail("SIGNER_UNAVAILABLE", "La autoridad persistente no está disponible o no supera self-test.", 9)

        draft["signing_key_id"] = signer.key_id
        signed = authority.sign_manifest(draft)
        verifier = InAppUpdater(trusted_keys={signer.key_id: signer.public_key_b64})
        verifier._manifest_from_payload(signed, require_signed=True)

        output = outbox_file()
        tmp = output.with_suffix(".tmp")
        tmp.write_text(json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, output)

        published, publish_status = publish_signed_manifest(signed, verifier)
        if not published:
            payload = {
                "ok": True,
                "status": "DEV302_SIGNED_NEEDS_UPLOAD",
                "version": VERSION,
                "signed_manifest": str(output),
                "publish_status": publish_status,
                "private_key_exported": False,
                "key_rotated": False,
                "installed": False,
            }
            write_status(payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 10

        staged = stage_candidate(InAppUpdater, signed, signer)
        payload = {
            "ok": True,
            "status": "DEV302_PUBLISHED_AND_STAGED",
            "version": VERSION,
            "release_sequence": RELEASE_SEQUENCE,
            "signing_key_id": signer.key_id,
            "package_sha256": PACKAGE_SHA256,
            "published": True,
            "publish_status": publish_status,
            "staged": staged,
            "private_key_exported": False,
            "key_rotated": False,
            "installed": False,
            "operator_install_confirmation_required": True,
            "previous_rejection_preserved_for_audit": True,
        }
        write_status(payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        return fail("DEV302_TRANSITION_FAILED", f"{type(exc).__name__}: {exc}", 30)


if __name__ == "__main__":
    raise SystemExit(main())
