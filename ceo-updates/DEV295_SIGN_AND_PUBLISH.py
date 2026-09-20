from __future__ import annotations

import hashlib
import json
import os
import shutil
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
VERSION = "1.5.71-rc1-update-confirm-bridge"
RELEASE_SEQUENCE = 295
RELEASE_ID = "dev295-1.5.71-rc1-update-confirm-bridge"
PACKAGE_NAME = "CEO_1.5.71-rc1-update-confirm-bridge.zip"
PACKAGE_SIZE = 1134619
PACKAGE_SHA256 = "10830bd64f5c65ec7a070497e6f08a227dfd76b7a2577de7a5570f389a24133a"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{PREFIX}"
DRAFT_URL = RAW_BASE + "DEV295_MANIFEST_UNSIGNED.json"
PACKAGE_URL = RAW_BASE + PACKAGE_NAME
MANIFEST_URL = RAW_BASE + "manifest.json"


def user_data_root() -> Path:
    return Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "CEO de IAs"


def outbox_file() -> Path:
    p = user_data_root() / "updates" / "outbox" / "DEV295_MANIFEST_SIGNED.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def status_file() -> Path:
    p = user_data_root() / "updates" / "bridge" / "DEV295_BRIDGE_STATUS.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_status(payload: dict) -> None:
    row = dict(payload)
    row.setdefault("generated_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
    tmp = status_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, status_file())


def fail(status: str, detail: str = "", code: int = 2) -> int:
    payload = {
        "ok": False,
        "status": status,
        "detail": detail[:2000],
        "signed_manifest": str(outbox_file()) if outbox_file().exists() else "",
        "private_key_exported": False,
    }
    write_status(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def fetch_bytes(url: str, timeout: int = 120) -> bytes:
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        url + sep + f"ceo_bridge={int(time.time())}",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
            "User-Agent": "CEO-de-IAs-DEV295-local-release-bridge",
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
        try:
            row = json.loads(pointer.read_text(encoding="utf-8"))
            root = Path(str(row.get("root") or "")).expanduser()
            if (root / "ceo_core" / "release_signing_authority.py").is_file():
                return root.resolve()
        except Exception:
            pass
    fallback = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "Programs" / "CEO de IAs"
    if (fallback / "ceo_core" / "release_signing_authority.py").is_file():
        return fallback.resolve()
    raise RuntimeError("CEO_INSTALL_ROOT_NOT_FOUND")


def verify_package_contract(package: Path) -> dict:
    if package.stat().st_size != PACKAGE_SIZE:
        raise RuntimeError(f"PACKAGE_SIZE_MISMATCH:{package.stat().st_size}")
    got = sha256_file(package)
    if got != PACKAGE_SHA256:
        raise RuntimeError(f"PACKAGE_SHA256_MISMATCH:{got}")
    with zipfile.ZipFile(package, "r") as zf:
        names = set(zf.namelist())
        if "CEO_UPDATE_PACKAGE.json" not in names:
            raise RuntimeError("PACKAGE_CONTRACT_MISSING")
        contract = json.loads(zf.read("CEO_UPDATE_PACKAGE.json").decode("utf-8"))
        if str(contract.get("app_version") or "") != VERSION:
            raise RuntimeError("PACKAGE_VERSION_MISMATCH")
        required = [str(x) for x in contract.get("required_paths") or []]
        missing = [x for x in required if x not in names]
        if missing:
            raise RuntimeError("PACKAGE_REQUIRED_PATHS_MISSING:" + ",".join(missing[:10]))
        for rel, expected in (contract.get("file_hashes") or {}).items():
            if rel not in names:
                raise RuntimeError(f"PACKAGE_HASHED_FILE_MISSING:{rel}")
            actual = hashlib.sha256(zf.read(rel)).hexdigest()
            if actual != str(expected):
                raise RuntimeError(f"PACKAGE_HASH_MISMATCH:{rel}")
        return contract


def run_git(args: list[str], cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
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


def attempt_publish(signed: dict, verifier) -> tuple[bool, str]:
    if shutil.which("git") is None:
        return False, "GIT_NOT_AVAILABLE"
    with tempfile.TemporaryDirectory(prefix="ceo-dev295-publish-") as td:
        repo = Path(td) / "repo"
        clone = run_git([
            "clone", "--depth", "1", "--single-branch", "--branch", BRANCH,
            f"https://github.com/{REPO}.git", str(repo),
        ], timeout=120)
        if clone.returncode != 0:
            return False, "GIT_AUTH_OR_CLONE_FAILED:" + (clone.stderr or clone.stdout)[-1000:]

        updates = repo / "ceo-updates"
        current_path = updates / "manifest.json"
        if current_path.is_file():
            try:
                current = json.loads(current_path.read_text(encoding="utf-8"))
                seq = int(current.get("release_sequence") or 0)
                if seq > RELEASE_SEQUENCE:
                    return False, f"REMOTE_SEQUENCE_AHEAD:{seq}"
                if seq == RELEASE_SEQUENCE:
                    verifier._manifest_from_payload(current, require_signed=True)
                    if str(current.get("release_id") or "") == RELEASE_ID:
                        return True, "ALREADY_PUBLISHED"
                    return False, "REMOTE_SEQUENCE_COLLISION"
            except Exception as exc:
                return False, f"REMOTE_MANIFEST_INVALID:{type(exc).__name__}:{exc}"

        signed_text = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        (updates / "DEV295_MANIFEST_SIGNED.json").write_text(signed_text, encoding="utf-8")
        current_path.write_text(signed_text, encoding="utf-8")

        for args in (["config", "user.name", "CEO de IAs"], ["config", "user.email", "ceo-local@localhost"]):
            cp = run_git(list(args), cwd=repo)
            if cp.returncode != 0:
                return False, "GIT_CONFIG_FAILED:" + (cp.stderr or cp.stdout)[-1000:]
        add = run_git(["add", "ceo-updates/manifest.json", "ceo-updates/DEV295_MANIFEST_SIGNED.json"], cwd=repo)
        if add.returncode != 0:
            return False, "GIT_STAGE_FAILED:" + (add.stderr or add.stdout)[-1000:]
        commit = run_git(["commit", "-m", "Activate DEV295 signed internal update"], cwd=repo)
        if commit.returncode not in (0, 1):
            return False, "GIT_COMMIT_FAILED:" + (commit.stderr or commit.stdout)[-1000:]
        push = run_git(["push", "origin", BRANCH], cwd=repo, timeout=120)
        if push.returncode != 0:
            return False, "GIT_PUSH_AUTH_REQUIRED:" + (push.stderr or push.stdout)[-1200:]

    try:
        remote = json.loads(fetch_bytes(MANIFEST_URL, 30).decode("utf-8"))
        verifier._manifest_from_payload(remote, require_signed=True)
        if str(remote.get("version") or "") != VERSION or int(remote.get("release_sequence") or 0) != RELEASE_SEQUENCE:
            return False, "REMOTE_VERIFY_WRONG_RELEASE"
        remote_pkg = fetch_bytes(PACKAGE_URL, 120)
        if len(remote_pkg) != PACKAGE_SIZE or hashlib.sha256(remote_pkg).hexdigest() != PACKAGE_SHA256:
            return False, "REMOTE_PACKAGE_VERIFY_FAILED"
    except Exception as exc:
        return False, f"REMOTE_VERIFY_FAILED:{type(exc).__name__}:{exc}"
    return True, "PUBLISHED_AND_VERIFIED"


def main() -> int:
    if os.name != "nt":
        return fail("WINDOWS_REQUIRED", "Este puente usa la autoridad de firma persistente de Windows.", 6)
    try:
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
        }
        for key, expected in exact.items():
            if draft.get(key) != expected:
                return fail("PREPARED_MANIFEST_MISMATCH", f"{key}: {draft.get(key)!r} != {expected!r}", 7)

        with tempfile.TemporaryDirectory(prefix="ceo-dev295-sign-") as td:
            package = Path(td) / PACKAGE_NAME
            package.write_bytes(fetch_bytes(PACKAGE_URL, 120))
            verify_package_contract(package)

            authority = ReleaseSigningAuthority()
            signer = authority.status()
            if not signer.configured or not signer.self_test:
                return fail("SIGNER_UNAVAILABLE", "La autoridad persistente no está configurada o no supera self-test. No se ha creado ni rotado ninguna clave.", 8)

            draft["signing_key_id"] = signer.key_id
            signed = authority.sign_manifest(draft)
            verifier = InAppUpdater(trusted_keys={signer.key_id: signer.public_key_b64})
            verifier._manifest_from_payload(signed, require_signed=True)

            output = outbox_file()
            tmp = output.with_suffix(".tmp")
            tmp.write_text(json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(tmp, output)

            published, publish_status = attempt_publish(signed, verifier)
            payload = {
                "ok": True,
                "status": "DEV295_PUBLISHED" if published else "DEV295_SIGNED_NEEDS_UPLOAD",
                "version": VERSION,
                "release_sequence": RELEASE_SEQUENCE,
                "release_id": RELEASE_ID,
                "signing_key_id": signer.key_id,
                "signer_self_test": signer.self_test,
                "package_sha256": PACKAGE_SHA256,
                "package_size": PACKAGE_SIZE,
                "signed_manifest": str(output),
                "published": published,
                "publish_status": publish_status,
                "private_key_exported": False,
                "key_rotated": False,
            }
            write_status(payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if published else 10
    except Exception as exc:
        return fail("DEV295_BRIDGE_FAILED", f"{type(exc).__name__}: {exc}", 30)


if __name__ == "__main__":
    raise SystemExit(main())
