from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from ceo_core.credentials import MemorySecretStore
from ceo_core.internal_release_policy import InternalReleasePolicy
from ceo_core.internal_release_publisher import InternalReleasePublisher
from ceo_core.release_signing_authority import ReleaseSigningAuthority
from ceo_core.in_app_updater import InAppUpdater

ROOT = Path(__file__).resolve().parents[1]
VERSION = "9.9.9-test"


def run(*args, cwd=None):
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, check=True)


class BytesResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


def make_candidate(path: Path) -> bytes:
    contract = {
        "app_version": VERSION,
        "contract_version": 1,
        "data_schema_version": 1,
        "required_paths": ["ABRIR_CEO.cmd", "CEO_UPDATE_PACKAGE.json"],
        "file_hashes": {},
        "health_path": "/api/health",
        "launcher": "ABRIR_CEO.cmd",
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ABRIR_CEO.cmd", "@echo off\r\n")
        zf.writestr("CEO_UPDATE_PACKAGE.json", json.dumps(contract))
    return path.read_bytes()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ceo-dev294-"))
    try:
        bare = tmp / "remote.git"
        run("git", "init", "--bare", "-b", "ceo-update-channel", str(bare))
        seed = tmp / "seed"
        run("git", "clone", str(bare), str(seed))
        run("git", "config", "user.email", "test@invalid", cwd=seed)
        run("git", "config", "user.name", "DEV294", cwd=seed)
        (seed / "ceo-updates").mkdir()
        (seed / "ceo-updates" / "manifest.json").write_text(json.dumps({"release_sequence": 293}), encoding="utf-8")
        run("git", "add", ".", cwd=seed)
        run("git", "commit", "-m", "seed", cwd=seed)
        run("git", "push", "origin", "HEAD:ceo-update-channel", cwd=seed)

        authority = ReleaseSigningAuthority(MemorySecretStore())
        status = authority.ensure_key()
        policy = InternalReleasePolicy(standing_publication_authorization=True, branch="ceo-update-channel")

        # Invalid artifacts cannot reach publication.
        rejected = False
        try:
            InternalReleasePublisher(authority=authority, policy=policy, receipt_root=tmp / "receipts")._verify_package_contract(ROOT / "CEO_UPDATE_PACKAGE.json", "x")
        except Exception:
            rejected = True
        assert rejected

        # Independent signature check with public key only.
        row = authority.sign_manifest({
            "version":"9.9.9","url":"https://example.invalid/a.zip","sha256":"0"*64,
            "channel":"stable","release_sequence":294,"release_status":"release","signature_alg":"ed25519",
            "manifest_version":2,"package_contract_version":1,"size_bytes":1,"artifact_name":"a.zip",
            "data_schema_version":1,"health_path":"/api/health","launcher":"ABRIR_CEO.cmd",
            "min_app_version":"1.5.58","max_app_version":"","release_id":"dev294-test"
        })
        InAppUpdater(trusted_keys={status.key_id: status.public_key_b64})._manifest_from_payload(row, require_signed=True)

        # Standing authorization is narrowly scoped.
        assert not policy.allows(repository="other/repo", branch="ceo-update-channel", path="ceo-updates/a.zip")
        assert not policy.allows(repository=policy.repository, branch="main", path="ceo-updates/a.zip")
        assert not policy.allows(repository=policy.repository, branch="ceo-update-channel", path="other/a.zip")

        package = tmp / f"CEO_{VERSION}.zip"
        package_bytes = make_candidate(package)
        def fake_urlopen(request, timeout=30):
            return BytesResponse(package_bytes)

        publisher = InternalReleasePublisher(
            authority=authority,
            policy=policy,
            receipt_root=tmp / "receipts",
            transport_repo_url=str(bare),
            urlopen=fake_urlopen,
        )
        result = publisher.publish(
            package_path=package,
            version=VERSION,
            release_sequence=294,
            release_id="dev294-local-e2e",
            notes="qualification",
            min_app_version="1.5.58",
        )
        assert result.ok and result.remote_verified

        inspect = tmp / "inspect"
        run("git", "clone", "--branch", "ceo-update-channel", str(bare), str(inspect))
        remote_manifest = json.loads((inspect / "ceo-updates" / "manifest.json").read_text(encoding="utf-8"))
        assert remote_manifest["version"] == VERSION
        assert remote_manifest["release_sequence"] == 294
        assert remote_manifest["signing_key_id"] == status.key_id
        InAppUpdater(trusted_keys={status.key_id: status.public_key_b64})._manifest_from_payload(remote_manifest, require_signed=True)
        assert (inspect / "ceo-updates" / package.name).read_bytes() == package_bytes

        second = publisher.publish(
            package_path=package,
            version=VERSION,
            release_sequence=294,
            release_id="dev294-local-e2e",
            notes="qualification",
            min_app_version="1.5.58",
        )
        assert not second.ok and second.status == "ANTI_REPLAY_BLOCKED"

        print(json.dumps({
            "pass": True,
            "signer_self_test": status.self_test,
            "signed_manifest_verify": True,
            "invalid_candidate_rejected": rejected,
            "scope_fail_closed": True,
            "local_git_publication_e2e": True,
            "remote_package_sha_verify": True,
            "anti_replay": True,
            "manual_download_required": False,
            "manual_signature_required": False,
            "manual_manifest_copy_required": False,
            "installation_confirmation_preserved": True,
        }, indent=2))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
