from __future__ import annotations

import base64
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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_bytes(url: str, timeout: int = 120) -> bytes:
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        url + sep + f"ceo_bootstrap={int(time.time())}",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
            "User-Agent": "CEO-de-IAs-DEV295-bootstrap",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def load_installed_root() -> Path:
    base = Path(os.getenv("CEO_DATA_DIR") or (Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "CEO de IAs"))
    current = base / "updates" / "current.json"
    if current.is_file():
        try:
            row = json.loads(current.read_text(encoding="utf-8"))
            root = Path(str(row.get("root") or "")).expanduser()
            if (root / "ceo_core").is_dir():
                return root.resolve()
        except Exception:
            pass
    # Fallback only to the current working tree; never scan arbitrary disks.
    cwd = Path.cwd().resolve()
    if (cwd / "ceo_core").is_dir():
        return cwd
    raise RuntimeError("CEO_INSTALL_ROOT_NOT_FOUND")


def verify_contract(package: Path) -> dict:
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
            raise RuntimeError("PACKAGE_REQUIRED_PATHS_MISSING:" + ",".join(missing[:8]))
        hashes = contract.get("file_hashes") or {}
        for rel, expected in hashes.items():
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
        ["git", *args], cwd=str(cwd) if cwd else None, env=env,
        capture_output=True, text=True, timeout=timeout, shell=False,
    )


def fail(status: str, detail: str = "", code: int = 2) -> int:
    print(json.dumps({"ok": False, "status": status, "detail": detail[:1000], "automatic_installation": False}, ensure_ascii=False))
    return code


def main() -> int:
    if os.name != "nt":
        return fail("WINDOWS_REQUIRED", "Persistent release signer is Windows-bound", 6)
    if shutil.which("git") is None:
        return fail("GIT_REQUIRED", "Git executable not available", 7)

    try:
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
                return fail("PREPARED_MANIFEST_MISMATCH", f"{key}: {draft.get(key)!r} != {expected!r}")

        with tempfile.TemporaryDirectory(prefix="ceo-dev295-bootstrap-") as td:
            tmp = Path(td)
            package = tmp / PACKAGE_NAME
            package.write_bytes(fetch_bytes(PACKAGE_URL, 120))
            verify_contract(package)

            root = load_installed_root()
            sys.path.insert(0, str(root))
            from ceo_core.release_signing_authority import ReleaseSigningAuthority
            from ceo_core.in_app_updater import InAppUpdater

            authority = ReleaseSigningAuthority()
            status = authority.status()
            if not status.configured or not status.self_test:
                return fail("SIGNER_UNAVAILABLE", "Persistent local signer is not configured/self-tested", 8)

            draft["signing_key_id"] = status.key_id
            signed = authority.sign_manifest(draft)
            verifier = InAppUpdater(trusted_keys={status.key_id: status.public_key_b64})
            verifier._manifest_from_payload(signed, require_signed=True)

            repo = tmp / "repo"
            clone = run_git(["clone", "--depth", "1", "--single-branch", "--branch", BRANCH,
                             f"https://github.com/{REPO}.git", str(repo)], timeout=120)
            if clone.returncode != 0:
                return fail("GITHUB_UPDATE_CHANNEL_AUTH_REQUIRED", clone.stderr or clone.stdout, 20)

            updates = repo / "ceo-updates"
            updates.mkdir(parents=True, exist_ok=True)
            signed_text = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            (updates / "DEV295_MANIFEST_SIGNED.json").write_text(signed_text, encoding="utf-8")
            (updates / "manifest.json").write_text(signed_text, encoding="utf-8")

            run_git(["config", "user.name", "CEO de IAs"], cwd=repo)
            run_git(["config", "user.email", "ceo-local@localhost"], cwd=repo)
            add = run_git(["add", "ceo-updates/manifest.json", "ceo-updates/DEV295_MANIFEST_SIGNED.json"], cwd=repo)
            if add.returncode != 0:
                return fail("GIT_STAGE_FAILED", add.stderr or add.stdout, 21)
            commit = run_git(["commit", "-m", "Activate DEV295 signed internal update"], cwd=repo)
            if commit.returncode not in (0, 1):
                return fail("GIT_COMMIT_FAILED", commit.stderr or commit.stdout, 22)
            push = run_git(["push", "origin", BRANCH], cwd=repo, timeout=120)
            if push.returncode != 0:
                return fail("GITHUB_UPDATE_CHANNEL_AUTH_REQUIRED", push.stderr or push.stdout, 23)

            remote = json.loads(fetch_bytes(MANIFEST_URL, 30).decode("utf-8"))
            verifier._manifest_from_payload(remote, require_signed=True)
            if str(remote.get("version") or "") != VERSION or int(remote.get("release_sequence") or 0) != RELEASE_SEQUENCE:
                return fail("REMOTE_ACTIVATION_VERIFY_FAILED", json.dumps(remote, ensure_ascii=False)[:800], 24)
            remote_package = fetch_bytes(PACKAGE_URL, 120)
            if len(remote_package) != PACKAGE_SIZE or hashlib.sha256(remote_package).hexdigest() != PACKAGE_SHA256:
                return fail("REMOTE_PACKAGE_VERIFY_FAILED", "remote bytes differ after activation", 25)

            print(json.dumps({
                "ok": True,
                "status": "DEV295_BRIDGE_PUBLISHED",
                "version": VERSION,
                "release_sequence": RELEASE_SEQUENCE,
                "signing_key_id": status.key_id,
                "package_sha256": PACKAGE_SHA256,
                "package_size": PACKAGE_SIZE,
                "operator_install_confirmation_required": True,
                "automatic_installation": False,
            }, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        return fail("DEV295_BOOTSTRAP_FAILED", f"{type(exc).__name__}: {exc}", 30)


if __name__ == "__main__":
    raise SystemExit(main())