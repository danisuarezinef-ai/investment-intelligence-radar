from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from .in_app_updater import InAppUpdater
from .internal_release_policy import InternalReleasePolicy, internal_release_policy
from .release_signing_authority import ReleaseSigningAuthority
from .runtime import user_data_root
from .update_channel import official_channel
from .release_firewall import ReleaseQualificationFirewall


@dataclass(slots=True)
class InternalReleasePublishResult:
    ok: bool
    status: str
    version: str
    package_name: str
    release_sequence: int
    repository: str
    branch: str
    commit: str = ""
    key_id: str = ""
    package_sha256: str = ""
    remote_verified: bool = False
    detail: str = ""


class InternalReleasePublisher:
    """Sign and publish CEO's own qualified update without operator file handling.

    The private signing key never leaves ReleaseSigningAuthority. Publication uses
    the machine's existing Git credential provider non-interactively; CEO never
    exports, prints or persists a GitHub password/token. Scope is restricted to the
    built-in update repository/branch/path by InternalReleasePolicy.
    """

    def __init__(
        self,
        *,
        authority: ReleaseSigningAuthority | None = None,
        policy: InternalReleasePolicy | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        urlopen: Callable[..., Any] | None = None,
        receipt_root: str | Path | None = None,
        transport_repo_url: str | None = None,
    ) -> None:
        self.authority = authority or ReleaseSigningAuthority()
        self.policy = policy or internal_release_policy()
        self.runner = runner or subprocess.run
        self.urlopen = urlopen or urllib.request.urlopen
        self.transport_repo_url = str(transport_repo_url or "").strip()
        base = Path(receipt_root) if receipt_root else user_data_root() / "updates" / "publication"
        self.receipt_root = base
        self.receipt_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _git(self, cwd: Path | None, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "Never"
        proc = self.runner(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            shell=False,
        )
        return proc

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _write_receipt(self, result: InternalReleasePublishResult, signed_manifest: dict[str, Any] | None = None) -> Path:
        payload = asdict(result)
        payload["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if signed_manifest:
            payload["manifest_fingerprint"] = signed_manifest.get("manifest_fingerprint", "")
            payload["signature_alg"] = signed_manifest.get("signature_alg", "")
        path = self.receipt_root / f"{result.release_sequence}-{result.version}.json"
        self._atomic_json(path, payload)
        return path

    def _build_manifest(
        self,
        *,
        package: Path,
        version: str,
        release_sequence: int,
        release_id: str,
        notes: str,
        min_app_version: str,
        repository: str,
        branch: str,
    ) -> dict[str, Any]:
        package_rel = f"{self.policy.path_prefix}{package.name}"
        if not self.policy.allows(repository=repository, branch=branch, path=package_rel):
            raise PermissionError("internal release target is outside the standing update-channel scope")
        url = f"https://raw.githubusercontent.com/{repository}/{quote(branch, safe='')}/{package_rel}"
        return {
            "artifact_name": package.name,
            "channel": "stable",
            "data_schema_version": 1,
            "health_path": "/api/health",
            "launcher": "ABRIR_CEO.cmd",
            "manifest_version": 2,
            "max_app_version": "",
            "min_app_version": str(min_app_version),
            "notes": str(notes),
            "package_contract_version": 1,
            "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "release_id": str(release_id),
            "release_sequence": int(release_sequence),
            "release_status": "release",
            "sha256": self._sha256(package),
            "signature_alg": "ed25519",
            "size_bytes": package.stat().st_size,
            "url": url,
            "version": str(version),
        }

    def _verify_package_contract(self, package: Path, expected_version: str) -> dict[str, Any]:
        import zipfile
        with zipfile.ZipFile(package, "r") as zf:
            names = set(zf.namelist())
            if "CEO_UPDATE_PACKAGE.json" not in names:
                raise RuntimeError("candidate lacks CEO_UPDATE_PACKAGE.json")
            contract = json.loads(zf.read("CEO_UPDATE_PACKAGE.json").decode("utf-8"))
            if str(contract.get("app_version") or "") != str(expected_version):
                raise RuntimeError("candidate version does not match package contract")
            missing = [x for x in contract.get("required_paths", []) if x not in names]
            if missing:
                raise RuntimeError(f"candidate contract missing required paths: {missing[:5]}")
            mismatches=[]
            for rel,expected in (contract.get("file_hashes") or {}).items():
                if rel not in names:
                    mismatches.append(rel); continue
                if hashlib.sha256(zf.read(rel)).hexdigest()!=str(expected):
                    mismatches.append(rel)
            if mismatches:
                raise RuntimeError(f"candidate contract hash mismatch: {mismatches[:5]}")
            return contract

    def _download_remote_bytes(self, url: str, *, timeout: int = 60) -> bytes:
        sep = "&" if "?" in url else "?"
        req = urllib.request.Request(
            url + sep + f"ceo_verify={int(time.time())}",
            headers={"User-Agent":"CEO-de-IAs-InternalRelease/2","Cache-Control":"no-cache, no-store","Pragma":"no-cache"},
        )
        with self.urlopen(req, timeout=timeout) as resp:
            return resp.read()

    def _remote_package_ok(self, manifest: dict[str, Any]) -> bool:
        # Test/local transports still get a true remote-repository readback, only via git clone
        # instead of raw.githubusercontent.com. Production uses the HTTP no-cache path below.
        if self.transport_repo_url:
            temp = Path(tempfile.mkdtemp(prefix="ceo-release-readback-"))
            try:
                clone = self._git(None, "clone", "--depth", "1", "--branch", self.policy.branch, self.transport_repo_url, str(temp / "repo"), timeout=120)
                if clone.returncode != 0:
                    return False
                candidate = temp / "repo" / self.policy.path_prefix / str(manifest.get("artifact_name") or "")
                return candidate.is_file() and candidate.stat().st_size == int(manifest.get("size_bytes") or 0) and self._sha256(candidate) == str(manifest.get("sha256") or "")
            finally:
                shutil.rmtree(temp, ignore_errors=True)
        try:
            data=self._download_remote_bytes(manifest["url"],timeout=60)
        except Exception:
            return False
        return len(data)==int(manifest.get("size_bytes") or 0) and hashlib.sha256(data).hexdigest()==str(manifest.get("sha256") or "")

    def _remote_verify(self, manifest: dict[str, Any], *, key_id: str, public_key_b64: str) -> bool:
        if not self._remote_package_ok(manifest):
            return False
        try:
            InAppUpdater(trusted_keys={key_id:public_key_b64})._manifest_from_payload(manifest,require_signed=True)
        except Exception:
            return False
        return True

    def publish(
        self,
        *,
        package_path: str | Path,
        version: str,
        release_sequence: int,
        release_id: str,
        notes: str,
        min_app_version: str,
        qualification: dict[str, Any] | None = None,
        repository: str | None = None,
        branch: str | None = None,
    ) -> InternalReleasePublishResult:
        # Publication is fail-closed at the final mutation boundary. No caller,
        # activator or bridge can turn a local candidate into a stable release
        # without the full production qualification record.
        ReleaseQualificationFirewall.require_stable(qualification)

        package=Path(package_path).resolve()
        if not package.is_file(): raise FileNotFoundError(package)
        if int(release_sequence)<=0: raise ValueError("release_sequence must be > 0")
        self._verify_package_contract(package,version)
        channel=official_channel()
        repository=str(repository or getattr(self.policy,"repository","") or channel.intended_repository).strip()
        branch=str(branch or self.policy.branch).strip()
        package_rel=f"{self.policy.path_prefix}{package.name}"
        if not self.policy.allows(repository=repository,branch=branch,path=package_rel):
            raise PermissionError("publication target rejected by internal release policy")
        status=self.authority.status()
        if not status.configured or not status.self_test:
            result=InternalReleasePublishResult(False,"SIGNER_UNAVAILABLE",version,package.name,int(release_sequence),repository,branch,detail="Persistent release signing authority is unavailable.")
            self._write_receipt(result); return result
        unsigned=self._build_manifest(package=package,version=version,release_sequence=release_sequence,release_id=release_id,notes=notes,min_app_version=min_app_version,repository=repository,branch=branch)
        unsigned["signing_key_id"]=status.key_id
        signed=self.authority.sign_manifest(unsigned)
        InAppUpdater(trusted_keys={status.key_id:status.public_key_b64})._manifest_from_payload(signed,require_signed=True)
        repo_url=self.transport_repo_url or f"https://github.com/{repository}.git"
        temp=Path(tempfile.mkdtemp(prefix="ceo-internal-release-"))
        try:
            clone=self._git(None,"clone","--depth","1","--branch",branch,repo_url,str(temp/"repo"),timeout=180)
            if clone.returncode!=0:
                result=InternalReleasePublishResult(False,"CHANNEL_READ_FAILED",version,package.name,int(release_sequence),repository,branch,key_id=status.key_id,package_sha256=unsigned["sha256"],detail=(clone.stderr or clone.stdout)[-600:]); self._write_receipt(result,signed); return result
            repo=temp/"repo"; manifest_path=repo/self.policy.path_prefix/"manifest.json"; manifest_path.parent.mkdir(parents=True,exist_ok=True)
            if manifest_path.is_file():
                current=json.loads(manifest_path.read_text(encoding="utf-8")); current_seq=int(current.get("release_sequence") or 0)
                if current_seq>=int(release_sequence):
                    result=InternalReleasePublishResult(False,"ANTI_REPLAY_BLOCKED",version,package.name,int(release_sequence),repository,branch,key_id=status.key_id,package_sha256=unsigned["sha256"],detail=f"remote release_sequence={current_seq} is not older"); self._write_receipt(result,signed); return result
            self._git(repo,"config","user.email","ceo-release@local.invalid"); self._git(repo,"config","user.name","CEO Internal Release")
            staged_path=repo/package_rel; needs_stage=True
            if staged_path.is_file():
                try: needs_stage=staged_path.stat().st_size!=package.stat().st_size or self._sha256(staged_path)!=unsigned["sha256"]
                except Exception: needs_stage=True
            stage_sha=""
            if needs_stage:
                shutil.copy2(package,staged_path)
                add=self._git(repo,"add","--",package_rel)
                if add.returncode!=0:
                    result=InternalReleasePublishResult(False,"COMMIT_FAILED",version,package.name,int(release_sequence),repository,branch,key_id=status.key_id,package_sha256=unsigned["sha256"],detail=(add.stderr or add.stdout)[-600:]); self._write_receipt(result,signed); return result
                commit=self._git(repo,"commit","-m",f"Stage {release_id} package")
                if commit.returncode!=0:
                    result=InternalReleasePublishResult(False,"COMMIT_FAILED",version,package.name,int(release_sequence),repository,branch,key_id=status.key_id,package_sha256=unsigned["sha256"],detail=(commit.stderr or commit.stdout)[-600:]); self._write_receipt(result,signed); return result
                sp=self._git(repo,"rev-parse","HEAD"); stage_sha=sp.stdout.strip() if sp.returncode==0 else ""
                push=self._git(repo,"push","origin",f"HEAD:{branch}",timeout=180)
                if push.returncode!=0:
                    result=InternalReleasePublishResult(False,"PUBLICATION_AUTH_OR_PUSH_FAILED",version,package.name,int(release_sequence),repository,branch,commit=stage_sha,key_id=status.key_id,package_sha256=unsigned["sha256"],detail="Existing non-interactive Git credentials were not sufficient for staging the update package."); self._write_receipt(result,signed); return result
            if not self._remote_package_ok(unsigned):
                result=InternalReleasePublishResult(False,"REMOTE_PACKAGE_VERIFY_FAILED",version,package.name,int(release_sequence),repository,branch,commit=stage_sha,key_id=status.key_id,package_sha256=unsigned["sha256"],remote_verified=False,detail="Staged package failed exact remote size/SHA-256 verification; active manifest was not advanced."); self._write_receipt(result,signed); return result
            receipt_manifest=repo/self.policy.path_prefix/f"{release_id}_MANIFEST_SIGNED.json"
            self._atomic_json(manifest_path,signed); self._atomic_json(receipt_manifest,signed)
            add=self._git(repo,"add","--",f"{self.policy.path_prefix}manifest.json",str(receipt_manifest.relative_to(repo)).replace("\\","/"))
            if add.returncode!=0:
                result=InternalReleasePublishResult(False,"COMMIT_FAILED",version,package.name,int(release_sequence),repository,branch,key_id=status.key_id,package_sha256=unsigned["sha256"],detail=(add.stderr or add.stdout)[-600:]); self._write_receipt(result,signed); return result
            commit=self._git(repo,"commit","-m",f"Activate {release_id}")
            if commit.returncode!=0:
                result=InternalReleasePublishResult(False,"COMMIT_FAILED",version,package.name,int(release_sequence),repository,branch,key_id=status.key_id,package_sha256=unsigned["sha256"],detail=(commit.stderr or commit.stdout)[-600:]); self._write_receipt(result,signed); return result
            sp=self._git(repo,"rev-parse","HEAD"); commit_sha=sp.stdout.strip() if sp.returncode==0 else ""
            push=self._git(repo,"push","origin",f"HEAD:{branch}",timeout=180)
            if push.returncode!=0:
                result=InternalReleasePublishResult(False,"PUBLICATION_AUTH_OR_PUSH_FAILED",version,package.name,int(release_sequence),repository,branch,commit=commit_sha,key_id=status.key_id,package_sha256=unsigned["sha256"],detail="Existing non-interactive Git credentials were not sufficient for activating the signed manifest."); self._write_receipt(result,signed); return result
            remote_ok=self._remote_verify(signed,key_id=status.key_id,public_key_b64=status.public_key_b64)
            result=InternalReleasePublishResult(bool(remote_ok),"PUBLISHED" if remote_ok else "REMOTE_VERIFY_FAILED",version,package.name,int(release_sequence),repository,branch,commit=commit_sha,key_id=status.key_id,package_sha256=unsigned["sha256"],remote_verified=bool(remote_ok),detail="Two-phase internal update published and remotely verified." if remote_ok else "Signed manifest was pushed but final remote verification failed.")
            self._write_receipt(result,signed); return result
        finally:
            shutil.rmtree(temp,ignore_errors=True)
