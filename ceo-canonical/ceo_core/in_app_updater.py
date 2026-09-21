from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .runtime import user_data_root
from .update_channel import official_channel
from .update_transaction import UpdateTransactionJournal
from .update_diagnostics import UpdateDiagnostics
from .update_state_machine import UpdateStateMachine
from .operator_update_summary import build_operator_update_summary
from .update_progress_telemetry_v2 import enrich_update_progress_v2
from .update_failure_evidence_v1 import UpdateFailureEvidenceRecorderV1
from .update_state_audit_v1 import UpdateStateAuditV1
from .dead_update_recovery_v2 import DeadUpdateRecoveryV2


@dataclass(slots=True)
class UpdateManifest:
    version: str
    url: str
    sha256: str
    channel: str = "stable"
    notes: str = ""
    launcher: str = "ABRIR_CEO.cmd"
    published_at: str = ""
    # Strict RC manifest contract. Defaults preserve direct/internal legacy tests;
    # remote manifests fetched by fetch_manifest() must use manifest_version=2.
    manifest_version: int = 1
    package_contract_version: int = 0
    size_bytes: int = 0
    artifact_name: str = ""
    min_app_version: str = "0.0.0"
    max_app_version: str = ""
    data_schema_version: int = 1
    signature_alg: str = ""
    signing_key_id: str = ""
    signature: str = ""
    health_path: str = "/api/health"
    release_status: str = "release"
    release_sequence: int = 0
    release_id: str = ""

    @property
    def has_artifact(self) -> bool:
        return self.release_status == "release"

    @property
    def strict(self) -> bool:
        return self.manifest_version >= 2


class InAppUpdater:
    """Human-gated, signed, side-by-side updater for CEO de IAs.

    Safety model:
      remote signed manifest -> atomic download -> SHA/size -> ZIP inspection ->
      package contract -> side-by-side staging -> explicit human activation ->
      restart health check -> confirm OR automatic rollback.

    The running version is never overwritten in place and automatic promotion is
    deliberately impossible through this class.
    """

    CONFIG_NAME = "config.json"
    CURRENT_NAME = "current.json"
    PREVIOUS_NAME = "previous.json"
    RECEIPT_NAME = ".ceo-update-receipt.json"
    PACKAGE_CONTRACT_NAME = "CEO_UPDATE_PACKAGE.json"
    TRUST_FILE_NAME = "update_trust.json"
    OPERATION_NAME = "operation.json"
    LOCK_NAME = "update.lock"
    MANIFEST_STATE_NAME = "manifest_state.json"
    PROGRESS_NAME = "progress.json"
    REJECTIONS_NAME = "rejections.json"
    STALE_OPERATION_SECONDS = 15 * 60
    MAX_DOWNLOAD_BYTES = 350 * 1024 * 1024
    MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
    MAX_FILES = 20000
    MAX_MANIFEST_BYTES = 2 * 1024 * 1024
    CURRENT_DATA_SCHEMA_VERSION = 1
    SUPPORTED_MANIFEST_VERSION = 2
    SUPPORTED_PACKAGE_CONTRACT_VERSION = 1
    REQUIRED_RUNTIME_PATHS = (
        "pyproject.toml",
        "scripts/ceo_stdlib_work_mode.py",
        "scripts/launch_current.py",
        "scripts/relaunch_after_update.py",
        "scripts/update_candidate_preflight.py",
        "scripts/install_windows_bootstrap.py",
        "scripts/bootstrap_release_signer.py",
        "scripts/sign_update_with_local_authority.py",
        "ceo_core/in_app_updater.py",
        "ceo_core/update_channel.py",
        "ceo_core/update_trust.json",
        "ceo_core/update_failure_lab.py",
        "ceo_core/update_diagnostics.py",
        "ceo_core/update_failure_evidence_v1.py",
        "ceo_core/core_health_contract_v2.py",
        "ceo_core/update_state_audit_v1.py",
        "ceo_core/rollback_guarantee_v2.py",
        "ceo_core/dead_update_recovery_v2.py",
        "ceo_core/update_progress_telemetry_v2.py",
        "ceo_core/update_failure_campaign_v2.py",
        "ceo_core/update_soak_v2.py",
        "ceo_core/release_readiness_v17.py",
        "ceo_core/campaign_baseline_snapshot_v2.py",
        "ceo_core/candidate_identity_lock_v1.py",
        "ceo_core/campaign_checkpoint_v2.py",
        "ceo_core/pre_cutover_recovery_point_v1.py",
        "ceo_core/startup_watchdog_v3.py",
        "ceo_core/update_root_cause_triage_v1.py",
        "ceo_core/productive_smoke_gate_v1.py",
        "ceo_core/one_shot_windows_campaign_executor_v1.py",
        "ceo_core/physical_campaign_soak_v1.py",
        "ceo_core/release_readiness_v18.py",
        "ceo_core/installed_runtime_gate_v1.py",
        "ceo_core/candidate_admission_seal_v1.py",
        "ceo_core/campaign_evidence_chain_v1.py",
        "ceo_core/safe_staging_rehearsal_v2.py",
        "ceo_core/restart_rehearsal_v2.py",
        "ceo_core/productive_continuity_gate_v2.py",
        "ceo_core/rollback_preservation_proof_v2.py",
        "ceo_core/diagnostic_support_bundle_v1.py",
        "ceo_core/physical_campaign_chaos_v2.py",
        "ceo_core/release_readiness_v19.py",
        "scripts/dev261_windows_preflight.py",
        "PREPARAR_CAMPANA_WINDOWS_DEV261.cmd",
        "ceo_core/physical_campaign_ticket_v1.py",
        "ceo_core/candidate_staleness_guard_v1.py",
        "ceo_core/pre_cutover_matrix_v1.py",
        "ceo_core/atomic_cutover_drill_v1.py",
        "ceo_core/crash_window_recovery_v1.py",
        "ceo_core/dual_activation_gate_v1.py",
        "ceo_core/user_state_migration_guard_v1.py",
        "ceo_core/campaign_exactly_once_guard_v1.py",
        "ceo_core/terminal_campaign_model_v1.py",
        "ceo_core/release_readiness_v20.py",
        "scripts/dev271_windows_campaign.py",
        "PREPARAR_CAMPANA_WINDOWS_DEV271.cmd",
        "ceo_core/update_state_machine.py",
        "ceo_core/update_transaction.py",
        "ceo_core/mobile_dev_queue.py",
        "ceo_core/self_dev_handoff.py",
        "ceo_core/release_readiness_v5.py",
        "ceo_core/update_failure_lab_v2.py",
        "ceo_core/physical_campaign_plan.py",
        "ceo_core/self_dev_inbox.py",
        "ceo_core/mobile_sync_v2.py",
        "ceo_core/operator_update_summary.py",
        "ceo_core/release_readiness_v6.py",
        "ceo_core/self_dev_reconciler.py",
        "ceo_core/update_failure_lab_v3.py",
        "ceo_core/update_recovery_planner_v2.py",
        "ceo_core/mobile_dev_queue_v2.py",
        "ceo_core/android_contract_v1.py",
        "ceo_core/evidence_bridge_v1.py",
        "ceo_core/executive_snapshot_v2.py",
        "ceo_core/compatibility_matrix_v1.py",
        "ceo_core/release_readiness_v7.py",
        "ceo_core/soak_guard_v2.py",
        "ceo_core/release_signing_authority.py",
        "ceo_core/credentials.py",
        "ceo_core/windows_shell.py",
        "assets/CEO_DE_IAS.ico",
        "assets/CEO_DE_IAS.png",
        "ceo_core/observability.py",
        "ceo_core/operational_resilience.py",
        "ceo_core/scheduler.py",
        "ceo_core/sqlite_store.py",
        "ceo_core/runtime.py",
        "ceo_core/models.py",
        "ceo_core/store.py",
        "ceo_core/quality_gate.py",
        "ceo_core/self_correction.py",
        "ceo_core/project_memory_v2.py",
        "ceo_core/dynamic_task_tree.py",
        "ceo_core/value_prioritization.py",
        "ceo_core/dependency_manager.py",
        "ceo_core/routing.py",
        "ceo_core/multi_ai_orchestrator.py",
        "ceo_core/consensus_verification.py",
        "ceo_core/application_recovery.py",
        "ceo_core/evidence_ledger_v2.py",
        "ceo_core/operations_dashboard.py",
        "ceo_core/operator_attention.py",
        "ceo_core/remote_control.py",
        "ceo_core/mission_supervisor_v2.py",
        "ceo_core/fair_work_allocator.py",
        "ceo_core/checkpoint_integrity_v2.py",
        "ceo_core/capability_policy_v2.py",
        "ceo_core/remote_session_v2.py",
        "ceo_core/mobile_compute_protocol.py",
        "ceo_core/tool_registry_v2.py",
        "ceo_core/canary_execution.py",
        "ceo_core/incident_manager_v2.py",
        "ceo_core/release_readiness_v3.py",
        "ceo_core/project_catalog.py",
        "ceo_core/portfolio_supervisor.py",
        "ceo_core/quota_governor_v2.py",
        "ceo_core/decision_trace_v3.py",
        "ceo_core/delegation_contracts_v2.py",
        "ceo_core/soak_guard_v1.py",
        "ceo_core/release_readiness_v4.py",
        "ceo_core/self_evolution_governor.py",
    )

    def __init__(
        self,
        data_root: str | Path | None = None,
        *,
        urlopen: Callable[..., Any] | None = None,
        trusted_keys: dict[str, str] | None = None,
    ):
        base = Path(data_root) if data_root else user_data_root()
        self.root = base / "updates"
        self.versions = self.root / "versions"
        self.downloads = self.root / "downloads"
        self.quarantine = self.root / "quarantine"
        self.root.mkdir(parents=True, exist_ok=True)
        self.versions.mkdir(parents=True, exist_ok=True)
        self.downloads.mkdir(parents=True, exist_ok=True)
        self.quarantine.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root / self.CONFIG_NAME
        self.current_path = self.root / self.CURRENT_NAME
        self.previous_path = self.root / self.PREVIOUS_NAME
        self._urlopen = urlopen or urllib.request.urlopen
        self._trusted_keys = trusted_keys if trusted_keys is not None else self._load_trusted_keys()

    def _note_nonfatal(self, area: str, exc: BaseException) -> None:
        """Persist best-effort updater failures instead of swallowing them.

        These events do not change transaction outcome, but they must remain
        observable so field failures never collapse into a disappearing console.
        """
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "area": str(area),
            "error_type": type(exc).__name__,
            "error": str(exc)[:1200],
        }
        path = self.root / "nonfatal-errors.jsonl"
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except Exception as log_exc:
            print(
                f"[CEO][UPDATE][WARN] {area}: {type(exc).__name__}: {exc}; "
                f"diagnostic-write-failed={type(log_exc).__name__}: {log_exc}",
                file=sys.stderr,
            )

    @staticmethod
    def _version_key(value: str) -> tuple[Any, ...]:
        """Comparable key for CEO version strings without external dependencies.

        Base numeric segments are normalized, stable releases sort after pre-releases,
        and common dev/alpha/beta/rc phases get deterministic ordering.  Signed
        release_sequence remains the authoritative tie-breaker once available.
        """
        text = (value or "0").strip().lower()
        base_text, sep, suffix = text.partition("-")
        nums = [int(x) for x in re.findall(r"\d+", base_text)] or [0]
        base = tuple((nums + [0, 0, 0, 0])[:4])
        if not sep or not suffix:
            return (*base, 1, 99, 0, "")
        phase_rank = 2
        phase_num = 0
        m = re.search(r"(?:^|[-_.])(dev|alpha|a|beta|b|rc)(\d*)", suffix)
        if m:
            phase_rank = {"dev": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "rc": 3}[m.group(1)]
            phase_num = int(m.group(2) or 0)
        return (*base, 0, phase_rank, phase_num, suffix)

    @classmethod
    def _version_tuple(cls, value: str) -> tuple[Any, ...]:
        # Backward-compatible internal name used by older call sites/tests.
        return cls._version_key(value)

    def _is_newer_release(self, manifest: UpdateManifest, current_version: str) -> bool:
        pointer = self.current_pointer() or {}
        installed_seq = int(pointer.get("release_sequence") or 0) if str(pointer.get("version") or "") == str(current_version) else 0
        if manifest.release_sequence and installed_seq:
            return manifest.release_sequence > installed_seq
        return self._version_key(manifest.version) > self._version_key(current_version)

    @staticmethod
    def _safe_version(value: str) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip()).strip(".-_")
        if not cleaned:
            raise ValueError("Versión de actualización inválida")
        return cleaned[:120]

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        """Atomic JSON write with bounded Windows sharing-violation recovery.

        Antivirus/indexers and concurrent readers can briefly deny os.replace()
        on Windows. Keep atomic semantics, retry only PermissionError, and fail
        closed after a bounded wait instead of rejecting a valid release.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            last_exc: PermissionError | None = None
            for attempt in range(40):
                try:
                    os.replace(tmp, path)
                    return
                except PermissionError as exc:
                    last_exc = exc
                    try:
                        if path.exists():
                            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
                    except OSError:
                        pass
                    if attempt >= 39:
                        raise
                    time.sleep(min(0.25, 0.025 * (attempt + 1)))
            if last_exc is not None:
                raise last_exc
        finally:
            tmp.unlink(missing_ok=True)

    def _load_trusted_keys(self) -> dict[str, str]:
        trust_path = Path(__file__).with_name(self.TRUST_FILE_NAME)
        built_in: dict[str, str] = {}
        try:
            payload = json.loads(trust_path.read_text(encoding="utf-8"))
            keys = payload.get("keys") if isinstance(payload, dict) else None
            if isinstance(keys, dict):
                built_in = {str(k): str(v) for k, v in keys.items() if str(k) and str(v)}
        except Exception:
            built_in = {}
        # DEV26: merge the user's persistent local release authority. The private
        # key stays inside Windows Credential Manager; only the derived public key
        # reaches the verifier. A local key may add trust, never replace a built-in
        # key with the same id but different material.
        try:
            from .release_signing_authority import load_local_release_public_keys
            local = load_local_release_public_keys()
            for key_id, public_b64 in local.items():
                if key_id in built_in and built_in[key_id] != public_b64:
                    continue
                built_in[key_id] = public_b64
        except Exception as exc:
            self._note_nonfatal("trusted_keys.local_authority", exc)
        return built_in

    def load_config(self) -> dict[str, Any]:
        channel = official_channel()
        base = {
            "manifest_url": channel.manifest_url,
            "channel": channel.channel or "stable",
            "auto_check": True,
            "product_id": channel.product_id,
            "bootstrap_transport": channel.bootstrap_transport,
            "intended_repository": channel.intended_repository,
            "channel_source": "built-in" if channel.manifest_url else "unconfigured",
        }
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in ("manifest_url", "channel", "auto_check"):
                    if key in data:
                        base[key] = data[key]
                if data.get("manifest_url"):
                    base["channel_source"] = "user-config"
        except Exception as exc:
            self._note_nonfatal("config.load", exc)
        env_url = os.getenv("CEO_UPDATE_MANIFEST_URL", "").strip()
        if env_url:
            base["manifest_url"] = env_url
            base["channel_source"] = "environment"
        return base

    def save_config(self, *, manifest_url: str, channel: str = "stable", auto_check: bool = True) -> dict[str, Any]:
        manifest_url = (manifest_url or "").strip()
        if manifest_url and urlparse(manifest_url).scheme.lower() != "https":
            raise ValueError("El canal de actualizaciones debe usar HTTPS")
        payload = {
            "manifest_url": manifest_url,
            "channel": (channel or "stable").strip() or "stable",
            "auto_check": bool(auto_check),
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._atomic_json(self.config_path, payload)
        return payload

    @staticmethod
    def _signed_payload_bytes(payload: dict[str, Any]) -> bytes:
        unsigned = {k: v for k, v in payload.items() if k not in {"signature", "manifest_fingerprint"}}
        return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def manifest_fingerprint(cls, payload: dict[str, Any]) -> str:
        return hashlib.sha256(cls._signed_payload_bytes(payload)).hexdigest()

    def _verify_manifest_signature(self, payload: dict[str, Any]) -> None:
        alg = str(payload.get("signature_alg") or "").lower().strip()
        key_id = str(payload.get("signing_key_id") or "").strip()
        signature_b64 = str(payload.get("signature") or "").strip()
        if alg != "ed25519":
            raise ValueError("Manifest sin firma Ed25519 compatible")
        if not key_id or key_id not in self._trusted_keys:
            raise ValueError("Manifest firmado con una clave no confiable")
        if not signature_b64:
            raise ValueError("Manifest sin firma criptográfica")
        try:
            public_raw = base64.b64decode(self._trusted_keys[key_id], validate=True)
            signature = base64.b64decode(signature_b64, validate=True)
            Ed25519PublicKey.from_public_bytes(public_raw).verify(signature, self._signed_payload_bytes(payload))
        except (ValueError, InvalidSignature, Exception) as exc:
            # Keep the message generic; malformed key/signature details do not help the UI.
            raise ValueError("Firma criptográfica del manifest inválida") from exc
        expected_fp = str(payload.get("manifest_fingerprint") or "").strip().lower()
        if expected_fp and expected_fp != self.manifest_fingerprint(payload):
            raise ValueError("Fingerprint lógico del manifest inválido")

    def _manifest_from_payload(self, payload: dict[str, Any], *, require_signed: bool = False) -> UpdateManifest:
        manifest_version = int(payload.get("manifest_version") or (2 if require_signed else 1))
        m = UpdateManifest(
            version=str(payload.get("version") or "").strip(),
            url=str(payload.get("url") or payload.get("package_url") or "").strip(),
            sha256=str(payload.get("sha256") or "").strip().lower(),
            channel=str(payload.get("channel") or "stable").strip() or "stable",
            notes=str(payload.get("notes") or ""),
            launcher=str(payload.get("launcher") or "ABRIR_CEO.cmd").strip() or "ABRIR_CEO.cmd",
            published_at=str(payload.get("published_at") or ""),
            manifest_version=manifest_version,
            package_contract_version=int(payload.get("package_contract_version") or 0),
            size_bytes=int(payload.get("size_bytes") or 0),
            artifact_name=str(payload.get("artifact_name") or "").strip(),
            min_app_version=str(payload.get("min_app_version") or "0.0.0").strip() or "0.0.0",
            max_app_version=str(payload.get("max_app_version") or "").strip(),
            data_schema_version=int(payload.get("data_schema_version") or 1),
            signature_alg=str(payload.get("signature_alg") or "").strip(),
            signing_key_id=str(payload.get("signing_key_id") or "").strip(),
            signature=str(payload.get("signature") or "").strip(),
            health_path=str(payload.get("health_path") or "/api/health").strip() or "/api/health",
            release_status=str(payload.get("release_status") or "release").strip().lower(),
            release_sequence=int(payload.get("release_sequence") or 0),
            release_id=str(payload.get("release_id") or "").strip(),
        )
        if not m.version:
            raise ValueError("Manifest sin versión")
        if m.release_status not in {"release", "current"}:
            raise ValueError("release_status de manifest inválido")
        if m.release_sequence < 0:
            raise ValueError("release_sequence inválido")
        if m.release_id and not re.fullmatch(r"[0-9A-Za-z._:-]{1,160}", m.release_id):
            raise ValueError("release_id inválido")
        if m.has_artifact:
            if urlparse(m.url).scheme.lower() != "https":
                raise ValueError("El paquete de actualización debe usar HTTPS")
            if not re.fullmatch(r"[0-9a-f]{64}", m.sha256):
                raise ValueError("SHA-256 de actualización inválido")
        elif m.url or m.sha256 or m.artifact_name or m.size_bytes:
            raise ValueError("Un manifest de estado current no debe anunciar artefacto")
        launcher = PurePosixPath(m.launcher.replace("\\", "/"))
        if launcher.is_absolute() or ".." in launcher.parts:
            raise ValueError("Launcher de actualización inseguro")
        health = PurePosixPath(m.health_path)
        if not m.health_path.startswith("/") or ".." in health.parts:
            raise ValueError("Ruta de health check inválida")
        if require_signed or m.strict:
            if m.manifest_version != self.SUPPORTED_MANIFEST_VERSION:
                raise ValueError(f"Versión de manifest no soportada: {m.manifest_version}")
            if m.package_contract_version != self.SUPPORTED_PACKAGE_CONTRACT_VERSION:
                raise ValueError("Contrato del paquete no soportado")
            if m.has_artifact:
                if m.size_bytes <= 0 or m.size_bytes > self.MAX_DOWNLOAD_BYTES:
                    raise ValueError("Tamaño declarado del paquete inválido")
                expected_name = Path(urlparse(m.url).path).name
                if not m.artifact_name or expected_name != m.artifact_name:
                    raise ValueError("artifact_name no coincide con la URL del paquete")
            elif m.package_contract_version not in {0, self.SUPPORTED_PACKAGE_CONTRACT_VERSION}:
                raise ValueError("Contrato de paquete inesperado para manifest current")
            if m.data_schema_version > self.CURRENT_DATA_SCHEMA_VERSION:
                raise ValueError("La actualización requiere un esquema de datos no soportado")
            self._verify_manifest_signature(payload)
        return m

    def fetch_manifest(self, manifest_url: str, *, timeout: int = 15) -> UpdateManifest:
        manifest_url = (manifest_url or "").strip()
        if urlparse(manifest_url).scheme.lower() != "https":
            raise ValueError("El manifest de actualización debe usar HTTPS")
        sep = "&" if "?" in manifest_url else "?"
        manifest_url = manifest_url + sep + f"ceo_check={int(time.time())}"
        req = urllib.request.Request(manifest_url, headers={"User-Agent":"CEO-de-IAs-Updater/2","Cache-Control":"no-cache, no-store","Pragma":"no-cache"})
        with self._urlopen(req, timeout=timeout) as resp:
            raw = resp.read(self.MAX_MANIFEST_BYTES + 1)
        if len(raw) > self.MAX_MANIFEST_BYTES:
            raise ValueError("Manifest demasiado grande")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Manifest inválido")
        return self._manifest_from_payload(payload, require_signed=True)

    def current_pointer(self) -> dict[str, Any] | None:
        try:
            row = json.loads(self.current_path.read_text(encoding="utf-8"))
            return row if isinstance(row, dict) else None
        except Exception:
            return None

    def previous_pointer(self) -> dict[str, Any] | None:
        try:
            row = json.loads(self.previous_path.read_text(encoding="utf-8"))
            return row if isinstance(row, dict) else None
        except Exception:
            return None

    def _compatibility_error(self, manifest: UpdateManifest, current_version: str) -> str | None:
        current = self._version_tuple(current_version)
        if current < self._version_tuple(manifest.min_app_version):
            return f"Requiere CEO >= {manifest.min_app_version}"
        if manifest.max_app_version and current > self._version_tuple(manifest.max_app_version):
            return f"No compatible con CEO > {manifest.max_app_version}"
        if manifest.data_schema_version > self.CURRENT_DATA_SCHEMA_VERSION:
            return "Esquema de datos no compatible"
        return None

    def operation_path(self) -> Path:
        return self.root / self.OPERATION_NAME

    def _record_operation(self, phase: str, **fields: Any) -> dict[str, Any]:
        row = {
            "phase": str(phase),
            "pid": os.getpid(),
            "updated_at_epoch": time.time(),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **fields,
        }
        self._atomic_json(self.operation_path(), row)
        return row

    def _clear_operation(self) -> None:
        self.operation_path().unlink(missing_ok=True)

    def _record_progress(self, phase: str, **fields: Any) -> dict[str, Any]:
        fields = enrich_update_progress_v2(str(phase), dict(fields))
        row = {
            "phase": str(phase),
            "updated_at_epoch": time.time(),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **fields,
        }
        self._atomic_json(self.root / self.PROGRESS_NAME, row)
        # DEV82: best-effort tamper-evident transaction history. Failure to write
        # observability evidence must never turn a safe update into an unsafe one.
        try:
            UpdateTransactionJournal(self.root).append(
                str(phase), version=str(fields.get("version") or ""),
                percent=fields.get("percent"), reason=str(fields.get("reason") or "")[:1000],
            )
        except Exception as exc:
            self._note_nonfatal("progress.transaction_journal", exc)
        if str(phase).lower() in {"preflight_failed", "rollback", "rolled_back"} or fields.get("reason"):
            try:
                UpdateFailureEvidenceRecorderV1(self.root).record(
                    str(phase), outcome="failure_or_recovery", reason=str(fields.get("reason") or ""),
                    version=str(fields.get("version") or ""), progress=row,
                    current=self.current_pointer(), previous=self.previous_pointer(),
                )
            except Exception as exc:
                self._note_nonfatal("progress.failure_evidence", exc)
        return row

    def progress(self) -> dict[str, Any]:
        row: dict[str, Any] = {}
        try:
            value = json.loads((self.root / self.PROGRESS_NAME).read_text(encoding="utf-8"))
            if isinstance(value, dict):
                row = value
        except Exception:
            row = {}
        try:
            restart = json.loads((self.root / "restart-progress.json").read_text(encoding="utf-8"))
            if isinstance(restart, dict) and float(restart.get("updated_at_epoch") or 0) >= float(row.get("updated_at_epoch") or 0):
                row = {**row, **restart}
        except Exception as exc:
            self._note_nonfatal("progress.restart_progress", exc)
        try:
            sup = json.loads((self.root / "last-restart-supervision.json").read_text(encoding="utf-8"))
            if isinstance(sup, dict):
                row["last_restart"] = sup
        except Exception as exc:
            self._note_nonfatal("progress.restart_supervision", exc)
        return row

    def diagnostics(self) -> dict[str, Any]:
        bundle = UpdateDiagnostics(self.root).bundle()
        bundle["state_audit"] = UpdateStateAuditV1(self.root).inspect(stale_after_seconds=self.STALE_OPERATION_SECONDS)
        return bundle

    def audit_state(self, *, stale_after_seconds: float | None = None) -> dict[str, Any]:
        stale = self.STALE_OPERATION_SECONDS if stale_after_seconds is None else float(stale_after_seconds)
        return UpdateStateAuditV1(self.root).inspect(stale_after_seconds=stale)

    def recover_dead_update(self, *, stale_after_seconds: float | None = None) -> dict[str, Any]:
        stale = self.STALE_OPERATION_SECONDS if stale_after_seconds is None else float(stale_after_seconds)
        return DeadUpdateRecoveryV2(self).recover(stale_after_seconds=stale)

    def update_view(self, *, current_version: str, include_remote: bool = False) -> dict[str, Any]:
        status = self.status(current_version=current_version, include_remote=include_remote)
        progress = self.progress()
        return UpdateStateMachine.view(status=status, progress=progress)

    def transaction_status(self) -> dict[str, Any]:
        journal = UpdateTransactionJournal(self.root)
        return {"integrity": journal.verify(), "recovery_hint": journal.recovery_hint()}

    def operator_summary(self, *, current_version: str, include_remote: bool = False) -> dict[str, Any]:
        return build_operator_update_summary(self, current_version=current_version, include_remote=include_remote)

    def lock_path(self) -> Path:
        return self.root / self.LOCK_NAME

    @contextmanager
    def _update_lock(self, purpose: str, *, stale_after_seconds: float | None = None):
        """Serialize update mutations and safely recover abandoned lock files."""
        stale = float(self.STALE_OPERATION_SECONDS if stale_after_seconds is None else stale_after_seconds)
        token = uuid.uuid4().hex
        path = self.lock_path()
        payload = {
            "token": token,
            "purpose": str(purpose),
            "pid": os.getpid(),
            "created_at_epoch": time.time(),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        for _ in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    os.write(fd, (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
                    os.fsync(fd)
                finally:
                    os.close(fd)
                break
            except FileExistsError:
                try:
                    row = json.loads(path.read_text(encoding="utf-8"))
                    age = time.time() - float(row.get("created_at_epoch") or 0.0)
                except Exception:
                    age = stale + 1
                if stale <= 0 or age >= stale:
                    path.unlink(missing_ok=True)
                    continue
                raise RuntimeError("Ya hay otra actualización de CEO en curso")
        else:
            raise RuntimeError("No se pudo adquirir el bloqueo de actualización")
        try:
            yield payload
        finally:
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                if row.get("token") == token:
                    path.unlink(missing_ok=True)
            except Exception as exc:
                self._note_nonfatal("lock.cleanup", exc)

    def _manifest_state_path(self) -> Path:
        return self.root / self.MANIFEST_STATE_NAME

    def _load_manifest_state(self) -> dict[str, Any]:
        try:
            row = json.loads(self._manifest_state_path().read_text(encoding="utf-8"))
            return row if isinstance(row, dict) else {}
        except Exception:
            return {}

    def _anti_replay_error(self, manifest: UpdateManifest) -> str | None:
        state = self._load_manifest_state()
        accepted_version = str(state.get("version") or "")
        accepted_seq = int(state.get("release_sequence") or 0)
        accepted_sha = str(state.get("sha256") or "")
        if accepted_version and self._version_tuple(manifest.version) < self._version_tuple(accepted_version):
            return f"Manifest de downgrade/replay rechazado: {manifest.version} < {accepted_version}"
        if manifest.release_sequence and accepted_seq:
            if manifest.release_sequence < accepted_seq:
                return f"release_sequence antiguo: {manifest.release_sequence} < {accepted_seq}"
            if manifest.release_sequence == accepted_seq:
                if manifest.version != accepted_version or (manifest.has_artifact and accepted_sha and manifest.sha256 != accepted_sha):
                    return "release_sequence reutilizado con contenido distinto"
        return None

    def _record_accepted_manifest(self, manifest: UpdateManifest) -> None:
        self._atomic_json(self._manifest_state_path(), {
            "version": manifest.version,
            "release_sequence": int(manifest.release_sequence or 0),
            "release_id": manifest.release_id,
            "sha256": manifest.sha256,
            "accepted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    def _rejections_path(self) -> Path:
        return self.root / self.REJECTIONS_NAME

    def _load_rejections(self) -> dict[str, Any]:
        try:
            row = json.loads(self._rejections_path().read_text(encoding="utf-8"))
            return row if isinstance(row, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _rejection_key(manifest: UpdateManifest) -> str:
        return f"{manifest.version}:{manifest.sha256}"

    def _reject_package(self, package: Path, manifest: UpdateManifest, reason: str) -> None:
        rows = self._load_rejections()
        key = self._rejection_key(manifest)
        dest = None
        try:
            if package.exists():
                dest = self.quarantine / f"{self._safe_version(manifest.version)}-{manifest.sha256[:12]}.zip"
                if dest.exists():
                    dest.unlink(missing_ok=True)
                os.replace(package, dest)
        except Exception:
            dest = None
        rows[key] = {
            "version": manifest.version,
            "sha256": manifest.sha256,
            "reason": str(reason)[:2000],
            "quarantined_package": str(dest) if dest else None,
            "rejected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        # Bounded ledger; latest 100 rejections are enough for operational diagnosis.
        if len(rows) > 100:
            rows = dict(list(rows.items())[-100:])
        self._atomic_json(self._rejections_path(), rows)

    def _ensure_not_rejected(self, manifest: UpdateManifest) -> None:
        row = self._load_rejections().get(self._rejection_key(manifest))
        if row:
            raise ValueError(f"Esta release fue rechazada anteriormente: {row.get('reason') or 'paquete inválido'}")

    def _staged_hashes(self, root: Path, launcher: str) -> dict[str, str]:
        rels = [launcher, *self.REQUIRED_RUNTIME_PATHS]
        hashes: dict[str, str] = {}
        for rel in rels:
            rel_norm = str(PurePosixPath(str(rel).replace("\\", "/")))
            path = root / Path(rel_norm)
            if not path.is_file():
                raise ValueError(f"Falta archivo crítico preparado: {rel_norm}")
            hashes[rel_norm] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes

    def _verify_staged_integrity(self, root: Path, row: dict[str, Any]) -> dict[str, Any]:
        expected = row.get("staged_file_hashes")
        if not isinstance(expected, dict) or not expected:
            raise ValueError("La actualización preparada no tiene sello de integridad local")
        verified = 0
        for rel, digest in expected.items():
            rel_norm = str(PurePosixPath(str(rel).replace("\\", "/")))
            p = root / Path(rel_norm)
            if not p.is_file():
                raise ValueError(f"Archivo preparado desaparecido: {rel_norm}")
            actual = hashlib.sha256(p.read_bytes()).hexdigest()
            if actual != str(digest):
                raise ValueError(f"La actualización preparada fue modificada: {rel_norm}")
            verified += 1
        return {"verified": True, "files_verified": verified}

    def recover_interrupted_update(self, *, stale_after_seconds: float | None = None) -> dict[str, Any]:
        """Recover update debris without ever deleting the known healthy version.

        Safe to call on every normal startup.  It removes stale partial downloads
        and extraction directories.  A stale pending-health pointer is rolled back
        to previous.json; a fresh pending activation is left untouched for the
        restart supervisor.
        """
        stale = float(self.STALE_OPERATION_SECONDS if stale_after_seconds is None else stale_after_seconds)
        now = time.time()
        removed_parts: list[str] = []
        removed_staging: list[str] = []
        for part in self.downloads.glob("*.part"):
            try:
                if stale <= 0 or now - part.stat().st_mtime >= stale:
                    part.unlink(missing_ok=True); removed_parts.append(part.name)
            except OSError:
                pass
        for part in self.downloads.glob(".*.part"):
            try:
                if stale <= 0 or now - part.stat().st_mtime >= stale:
                    part.unlink(missing_ok=True); removed_parts.append(part.name)
            except OSError:
                pass
        for d in self.versions.iterdir() if self.versions.exists() else ():
            if not d.is_dir() or not d.name.startswith("ceo-update-"):
                continue
            try:
                if stale <= 0 or now - d.stat().st_mtime >= stale:
                    shutil.rmtree(d, ignore_errors=True); removed_staging.append(d.name)
            except OSError:
                pass

        pointer = self.current_pointer()
        rolled_back = None
        if pointer and pointer.get("status") == "pending_health":
            activated_epoch = float(pointer.get("activated_at_epoch") or 0.0)
            # Legacy pointers lack epoch; operation journal supplies a conservative
            # freshness boundary.  Never roll back a just-created activation.
            age = now - activated_epoch if activated_epoch else None
            if age is None:
                try:
                    op = json.loads(self.operation_path().read_text(encoding="utf-8"))
                    op_epoch = float(op.get("updated_at_epoch") or 0.0)
                    age = now - op_epoch if op_epoch else None
                except Exception:
                    age = None
            if stale <= 0 or (age is not None and age >= stale):
                rolled_back = self.rollback(reason="interrupted/stale pending activation", failed_version=str(pointer.get("version") or ""))

        op_path = self.operation_path()
        cleared_operation = False
        if op_path.exists():
            try:
                op = json.loads(op_path.read_text(encoding="utf-8"))
                age = now - float(op.get("updated_at_epoch") or 0.0)
                if stale <= 0 or age >= stale:
                    op_path.unlink(missing_ok=True); cleared_operation = True
            except Exception:
                op_path.unlink(missing_ok=True); cleared_operation = True
        cleared_lock = False
        lock = self.lock_path()
        if lock.exists():
            try:
                row = json.loads(lock.read_text(encoding="utf-8"))
                age = now - float(row.get("created_at_epoch") or 0.0)
                if stale <= 0 or age >= stale:
                    lock.unlink(missing_ok=True); cleared_lock = True
            except Exception:
                lock.unlink(missing_ok=True); cleared_lock = True
        return {
            "removed_partial_downloads": removed_parts,
            "removed_staging_dirs": removed_staging,
            "rolled_back": rolled_back,
            "cleared_operation": cleared_operation,
            "cleared_update_lock": cleared_lock,
        }

    def status(self, *, current_version: str, include_remote: bool = False) -> dict[str, Any]:
        cfg = self.load_config()
        result: dict[str, Any] = {
            "current_version": current_version,
            "configured": bool(cfg.get("manifest_url")),
            "manifest_url": cfg.get("manifest_url") or "",
            "channel": cfg.get("channel") or "stable",
            "auto_check": bool(cfg.get("auto_check", True)),
            "pointer": self.current_pointer(),
            "previous_pointer": self.previous_pointer(),
            "staged": self.list_staged(),
            "signed_manifest_required": True,
            "channel_source": cfg.get("channel_source"),
            "product_id": cfg.get("product_id", "ceo-de-ias"),
            "bootstrap_transport": cfg.get("bootstrap_transport", ""),
            "intended_repository": cfg.get("intended_repository", ""),
        }
        if include_remote and result["configured"]:
            try:
                manifest = self.fetch_manifest(result["manifest_url"])
                if manifest.channel != result["channel"]:
                    raise ValueError(f"El manifest pertenece al canal {manifest.channel}, no a {result['channel']}")
                compatibility = self._compatibility_error(manifest, current_version)
                replay_error = self._anti_replay_error(manifest)
                if replay_error:
                    compatibility = replay_error
                result.update({
                    "remote": asdict(manifest),
                    "available": manifest.has_artifact and self._is_newer_release(manifest, current_version) and compatibility is None,
                    "compatible": compatibility is None,
                    "compatibility_error": compatibility,
                    "error": None,
                })
            except Exception as exc:
                result.update({"available": False, "compatible": False, "error": f"{type(exc).__name__}: {exc}"})
        else:
            result.setdefault("available", False)
        return result

    def _download(self, manifest: UpdateManifest) -> Path:
        safe = self._safe_version(manifest.version)
        artifact = manifest.artifact_name or f"ceo-{safe}.zip"
        if Path(artifact).name != artifact:
            raise ValueError("Nombre de artefacto inseguro")
        final = self.downloads / artifact
        # Reuse only a byte-identical previously verified download.
        if final.is_file():
            data_size = final.stat().st_size
            digest = hashlib.sha256(final.read_bytes()).hexdigest()
            expected_size_ok = not manifest.size_bytes or data_size == manifest.size_bytes
            if digest == manifest.sha256 and expected_size_ok:
                return final
            final.unlink(missing_ok=True)
        part = self.downloads / f".{artifact}.{os.getpid()}.{uuid.uuid4().hex}.part"
        self._record_operation("downloading", version=manifest.version, artifact=artifact, part=str(part))
        self._record_progress("downloading", version=manifest.version, artifact=artifact, bytes_downloaded=0, bytes_expected=int(manifest.size_bytes or 0), percent=0)
        req = urllib.request.Request(manifest.url, headers={"User-Agent": "CEO-de-IAs-Updater/2"})
        h = hashlib.sha256()
        total = 0
        try:
            with self._urlopen(req, timeout=120) as resp, part.open("wb") as f:
                length = resp.headers.get("Content-Length") if getattr(resp, "headers", None) is not None else None
                if length and int(length) > self.MAX_DOWNLOAD_BYTES:
                    raise ValueError("Paquete de actualización demasiado grande")
                if manifest.size_bytes and length and int(length) != manifest.size_bytes:
                    raise ValueError("Content-Length no coincide con el manifest")
                while True:
                    block = resp.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > self.MAX_DOWNLOAD_BYTES:
                        raise ValueError("Paquete de actualización demasiado grande")
                    h.update(block)
                    f.write(block)
                    expected = int(manifest.size_bytes or 0)
                    percent = int(min(70, round((total / expected) * 70))) if expected > 0 else None
                    self._record_progress("downloading", version=manifest.version, artifact=artifact, bytes_downloaded=total, bytes_expected=expected, percent=percent)
                f.flush()
                os.fsync(f.fileno())
            if manifest.size_bytes and total != manifest.size_bytes:
                raise ValueError("El tamaño descargado no coincide con el manifest")
            if h.hexdigest().lower() != manifest.sha256.lower():
                raise ValueError("El SHA-256 descargado no coincide con el manifest")
            os.replace(part, final)
            self._record_operation("downloaded", version=manifest.version, artifact=artifact, final=str(final))
            self._record_progress("downloaded", version=manifest.version, artifact=artifact, bytes_downloaded=total, bytes_expected=int(manifest.size_bytes or total), percent=72)
            return final
        except Exception:
            part.unlink(missing_ok=True)
            self._clear_operation()
            raise

    @staticmethod
    def _unsafe_zip_member(info: zipfile.ZipInfo) -> bool:
        p = PurePosixPath(info.filename.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts:
            return True
        mode = (info.external_attr >> 16) & 0xFFFF
        return stat.S_ISLNK(mode)

    def _inspect_zip(self, package: Path) -> list[zipfile.ZipInfo]:
        with zipfile.ZipFile(package, "r") as zf:
            infos = zf.infolist()
            if len(infos) > self.MAX_FILES:
                raise ValueError("Demasiados archivos en la actualización")
            total = 0
            seen: set[str] = set()
            for info in infos:
                if self._unsafe_zip_member(info):
                    raise ValueError(f"Ruta insegura en actualización: {info.filename}")
                normalized = str(PurePosixPath(info.filename.replace("\\", "/")))
                if normalized in seen and not info.is_dir():
                    raise ValueError(f"Archivo duplicado en actualización: {normalized}")
                seen.add(normalized)
                total += int(info.file_size)
                if total > self.MAX_UNCOMPRESSED_BYTES:
                    raise ValueError("Actualización demasiado grande al descomprimir")
            return infos

    @staticmethod
    def _payload_root(extracted: Path, launcher: str) -> Path:
        direct = extracted / Path(launcher)
        if direct.is_file():
            return extracted
        children = [p for p in extracted.iterdir() if p.is_dir()]
        files = [p for p in extracted.iterdir() if p.is_file()]
        if len(children) == 1 and not files and (children[0] / Path(launcher)).is_file():
            return children[0]
        raise ValueError(f"El paquete no contiene el launcher esperado: {launcher}")

    @staticmethod
    def _zip_prefix(zf: zipfile.ZipFile, launcher: str) -> str:
        names = {str(PurePosixPath(i.filename.replace("\\", "/"))) for i in zf.infolist() if not i.is_dir()}
        launcher_norm = str(PurePosixPath(launcher.replace("\\", "/")))
        if launcher_norm in names:
            return ""
        parts = [PurePosixPath(n).parts for n in names if n]
        top = {p[0] for p in parts if p}
        if len(top) == 1:
            prefix = next(iter(top)).rstrip("/") + "/"
            if prefix + launcher_norm in names:
                return prefix
        raise ValueError(f"El paquete no contiene el launcher esperado: {launcher}")

    def _validate_package_contract(self, package: Path, manifest: UpdateManifest) -> dict[str, Any]:
        if not manifest.strict:
            return {"verified": False, "legacy_direct": True}
        with zipfile.ZipFile(package, "r") as zf:
            prefix = self._zip_prefix(zf, manifest.launcher)
            contract_name = prefix + self.PACKAGE_CONTRACT_NAME
            try:
                raw = zf.read(contract_name)
            except KeyError as exc:
                raise ValueError(f"Falta {self.PACKAGE_CONTRACT_NAME} en el paquete") from exc
            if len(raw) > 1024 * 1024:
                raise ValueError("Contrato interno del paquete demasiado grande")
            contract = json.loads(raw.decode("utf-8"))
            if not isinstance(contract, dict):
                raise ValueError("Contrato interno del paquete inválido")
            if int(contract.get("contract_version") or 0) != manifest.package_contract_version:
                raise ValueError("Versión de contrato interno no coincide con el manifest")
            if str(contract.get("app_version") or "") != manifest.version:
                raise ValueError("Versión interna del paquete no coincide con el manifest")
            if int(contract.get("data_schema_version") or 0) != manifest.data_schema_version:
                raise ValueError("Esquema interno del paquete no coincide con el manifest")
            if str(contract.get("launcher") or "") != manifest.launcher:
                raise ValueError("Launcher interno no coincide con el manifest")
            required = [manifest.launcher, self.PACKAGE_CONTRACT_NAME, *self.REQUIRED_RUNTIME_PATHS]
            declared = {str(PurePosixPath(str(p).replace("\\", "/"))) for p in (contract.get("required_paths") or [])}
            file_hashes = contract.get("file_hashes") or {}
            if not isinstance(file_hashes, dict):
                raise ValueError("file_hashes inválido en contrato del paquete")
            names = {str(PurePosixPath(i.filename.replace("\\", "/"))) for i in zf.infolist() if not i.is_dir()}
            verified_hashes = 0
            for rel in required:
                rel_norm = str(PurePosixPath(rel.replace("\\", "/")))
                if rel_norm not in declared:
                    raise ValueError(f"Ruta esencial no declarada en contrato: {rel_norm}")
                archive_name = prefix + rel_norm
                if archive_name not in names:
                    raise ValueError(f"Paquete incompleto: falta {rel_norm}")
                # The contract file itself cannot contain a hash of its final bytes
                # without a recursive fixed-point. Its integrity is already covered
                # by the signed outer manifest + ZIP SHA-256, so hash every other
                # runtime-critical file and only require the contract to exist.
                if rel_norm == self.PACKAGE_CONTRACT_NAME:
                    continue
                expected = str(file_hashes.get(rel_norm) or "").lower()
                if not re.fullmatch(r"[0-9a-f]{64}", expected):
                    raise ValueError(f"Falta hash contractual válido para {rel_norm}")
                actual = hashlib.sha256(zf.read(archive_name)).hexdigest()
                if actual != expected:
                    raise ValueError(f"Hash interno no coincide para {rel_norm}")
                verified_hashes += 1
            return {
                "verified": True,
                "contract_version": manifest.package_contract_version,
                "prefix": prefix,
                "required_paths_verified": len(required),
                "hashes_verified": verified_hashes,
            }

    def _ensure_no_pending_activation(self) -> None:
        pointer = self.current_pointer() or {}
        if str(pointer.get("status") or "") == "pending_health":
            raise RuntimeError("Hay una activación pendiente de health-check; no se puede preparar otra versión todavía")

    def stage(self, manifest: UpdateManifest) -> dict[str, Any]:
        self._ensure_no_pending_activation()
        with self._update_lock("stage"):
            self._ensure_no_pending_activation()
            return self._stage_unlocked(manifest)

    def _stage_unlocked(self, manifest: UpdateManifest) -> dict[str, Any]:
        replay_error = self._anti_replay_error(manifest)
        if replay_error:
            raise ValueError(replay_error)
        self._ensure_not_rejected(manifest)
        safe = self._safe_version(manifest.version)
        package = self._download(manifest)
        try:
            self._record_progress("verifying", version=manifest.version, percent=78)
            infos = self._inspect_zip(package)
            contract = self._validate_package_contract(package, manifest)
            self._record_progress("extracting", version=manifest.version, percent=86)
        except Exception as exc:
            self._reject_package(package, manifest, f"{type(exc).__name__}: {exc}")
            self._clear_operation()
            raise
        final_root = self.versions / safe
        if final_root.exists():
            receipt = final_root / self.RECEIPT_NAME
            try:
                row = json.loads(receipt.read_text(encoding="utf-8"))
                strict_ok = (not manifest.strict) or bool(row.get("contract_verified"))
                if row.get("sha256") == manifest.sha256 and (final_root / manifest.launcher).is_file() and strict_ok:
                    self._verify_staged_integrity(final_root, row)
                    self._record_accepted_manifest(manifest)
                    return row
            except Exception as exc:
                self._note_nonfatal("stage.existing_receipt", exc)
        temp = Path(tempfile.mkdtemp(prefix=f"ceo-update-{safe}-", dir=str(self.versions)))
        backup: Path | None = None
        try:
            with zipfile.ZipFile(package, "r") as zf:
                zf.extractall(temp)
            payload = self._payload_root(temp, manifest.launcher)
            if payload != temp:
                moved = temp.with_name(temp.name + "-payload")
                payload.rename(moved)
                shutil.rmtree(temp, ignore_errors=True)
                temp = moved
            staged_hashes = self._staged_hashes(temp, manifest.launcher)
            receipt = {
                "version": manifest.version,
                "channel": manifest.channel,
                "sha256": manifest.sha256,
                "size_bytes": package.stat().st_size,
                "package": str(package),
                "root": str(final_root),
                "launcher": manifest.launcher,
                "notes": manifest.notes,
                "published_at": manifest.published_at,
                "manifest_version": manifest.manifest_version,
                "package_contract_version": manifest.package_contract_version,
                "contract_verified": bool(contract.get("verified")),
                "contract": contract,
                "data_schema_version": manifest.data_schema_version,
                "health_path": manifest.health_path,
                "release_sequence": manifest.release_sequence,
                "release_id": manifest.release_id,
                "file_count": len(infos),
                "staged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "staged_file_hashes": staged_hashes,
                "staged_integrity_files": len(staged_hashes),
                "installed": False,
                "health_confirmed": False,
                "automatic_promotion": False,
                "requires_human_confirmation": True,
            }
            self._atomic_json(temp / self.RECEIPT_NAME, receipt)
            if final_root.exists():
                backup = self.quarantine / f"{safe}-{uuid.uuid4().hex}"
                os.replace(final_root, backup)
            os.replace(temp, final_root)
            if backup is not None:
                shutil.rmtree(backup, ignore_errors=True)
            self._record_accepted_manifest(manifest)
            self._record_progress("ready_to_install", version=manifest.version, percent=100)
            self._clear_operation()
            return receipt
        except Exception:
            if temp.exists() and temp != final_root:
                shutil.rmtree(temp, ignore_errors=True)
            if backup is not None and backup.exists():
                if final_root.exists():
                    shutil.rmtree(final_root, ignore_errors=True)
                os.replace(backup, final_root)
            self._clear_operation()
            raise

    def stage_latest(self, *, current_version: str) -> dict[str, Any]:
        self._ensure_no_pending_activation()
        cfg = self.load_config()
        url = str(cfg.get("manifest_url") or "").strip()
        if not url:
            raise ValueError("No hay canal de actualizaciones configurado")
        manifest = self.fetch_manifest(url)
        if manifest.channel != str(cfg.get("channel") or "stable"):
            raise ValueError("El canal del manifest no coincide con el canal configurado")
        compatibility = self._compatibility_error(manifest, current_version)
        if compatibility:
            raise ValueError(f"Actualización incompatible: {compatibility}")
        replay_error = self._anti_replay_error(manifest)
        if replay_error:
            raise ValueError(replay_error)
        if not manifest.has_artifact or not self._is_newer_release(manifest, current_version):
            return {"available": False, "version": manifest.version, "detail": "Ya estás en la versión más reciente"}
        row = self.stage(manifest)
        return {"available": True, "staged": True, "receipt": row}

    def list_staged(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not self.versions.exists():
            return rows
        rolled_back_version = ""
        try:
            restart = json.loads((self.root / "restart-progress.json").read_text(encoding="utf-8"))
            if isinstance(restart, dict) and str(restart.get("phase") or "") == "rolled_back":
                rolled_back_version = str(restart.get("version") or "")
        except Exception as exc:
            self._note_nonfatal("staged.rollback_marker", exc)
        for d in sorted(self.versions.iterdir(), reverse=True):
            if not d.is_dir() or d.name.startswith("ceo-update-"):
                continue
            try:
                row = json.loads((d / self.RECEIPT_NAME).read_text(encoding="utf-8"))
                if isinstance(row, dict):
                    if rolled_back_version and str(row.get("version") or "") == rolled_back_version:
                        row["rolled_back"] = True
                        row.setdefault("rollback_reason", "restart supervisor recorded rollback")
                    row["root"] = str(d)
                    rows.append(row)
            except Exception:
                continue
        return rows

    def preflight_staged(self, version: str, *, python_executable: str | None = None, timeout: float = 45.0) -> dict[str, Any]:
        """Prove a staged candidate can boot before the active pointer changes.

        The probe uses a disposable CEO_DATA_DIR and the candidate's real HTTP health
        endpoint.  Failure cannot interrupt the currently running version.
        """
        self._ensure_no_pending_activation()
        safe = self._safe_version(version)
        root = self.versions / safe
        receipt_path = root / self.RECEIPT_NAME
        if not receipt_path.is_file():
            raise ValueError("La versión solicitada no está preparada")
        row = json.loads(receipt_path.read_text(encoding="utf-8"))
        if row.get("rolled_back"):
            raise ValueError("La versión preparada está marcada como rollback y no puede reactivarse")
        self._verify_staged_integrity(root, row)
        probe = root / "scripts" / "update_candidate_preflight.py"
        if not probe.is_file():
            raise ValueError("La actualización no incluye la prueba previa de arranque")
        sandbox_parent = self.root / "preflight-sandboxes"
        log_path = self.root / "preflight-latest.log"
        cmd = [python_executable or sys.executable, "-u", str(probe), "--root", str(root), "--expected-version", str(row.get("version") or version), "--sandbox-parent", str(sandbox_parent), "--timeout", str(max(5.0, float(timeout) - 5.0))]
        self._record_progress("preflight", version=str(row.get("version") or version), percent=5)
        try:
            cp = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=max(10.0, float(timeout)))
        except subprocess.TimeoutExpired as exc:
            text = (exc.stdout or "") + "\n" + (exc.stderr or "")
            log_path.write_text(text[-20000:], encoding="utf-8")
            row.update({"preflight_failed": True, "preflight_error": "timeout", "preflight_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
            self._atomic_json(receipt_path, row)
            self._record_progress("preflight_failed", version=str(row.get("version") or version), percent=100, reason="timeout")
            raise RuntimeError("La nueva versión no superó la prueba previa de arranque (timeout)")
        output = ((cp.stdout or "") + ("\n" + cp.stderr if cp.stderr else "")).strip()
        log_path.write_text(output[-20000:] + ("\n" if output else ""), encoding="utf-8")
        if cp.returncode != 0:
            reason = output.splitlines()[-1] if output else f"exit code {cp.returncode}"
            row.update({"preflight_failed": True, "preflight_error": reason[:1000], "preflight_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
            self._atomic_json(receipt_path, row)
            self._record_progress("preflight_failed", version=str(row.get("version") or version), percent=100, reason=reason[:1000])
            raise RuntimeError(f"La nueva versión no superó la prueba previa de arranque: {reason[:500]}")
        row.update({"preflight_failed": False, "preflight_ok": True, "preflight_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "preflight_log": str(log_path)})
        self._atomic_json(receipt_path, row)
        self._record_progress("preflight_ok", version=str(row.get("version") or version), percent=20)
        return {"ok": True, "version": str(row.get("version") or version), "log": str(log_path)}

    def activate(self, version: str) -> dict[str, Any]:
        # DEV265/269: a second activation while the first candidate is still
        # pending health must never overwrite previous.json.  That would destroy
        # the known-good rollback target.  Guard both before and after taking the
        # mutation lock so duplicate clicks/retries fail closed.
        self._ensure_no_pending_activation()
        with self._update_lock("activate"):
            self._ensure_no_pending_activation()
            return self._activate_unlocked(version)

    def _activate_unlocked(self, version: str) -> dict[str, Any]:
        """Human-confirmed pointer switch, pending health confirmation.

        This does not mark the new version healthy/installed. The restart supervisor
        must call confirm_health(); otherwise it rolls back to previous.json.
        """
        safe = self._safe_version(version)
        root = self.versions / safe
        receipt_path = root / self.RECEIPT_NAME
        if not receipt_path.is_file():
            raise ValueError("La versión solicitada no está preparada")
        row = json.loads(receipt_path.read_text(encoding="utf-8"))
        if int(row.get("manifest_version") or 1) >= 2 and not row.get("contract_verified"):
            raise ValueError("La versión no superó el contrato integral de paquete")
        if int(row.get("manifest_version") or 1) >= 2 and not row.get("preflight_ok"):
            raise ValueError("La versión no superó la prueba previa de arranque")
        launcher = str(row.get("launcher") or "ABRIR_CEO.cmd")
        launcher_path = root / launcher
        if not launcher_path.is_file():
            raise ValueError("Launcher de la actualización no encontrado")
        integrity = self._verify_staged_integrity(root, row)
        previous = self.current_pointer()
        if previous:
            self._atomic_json(self.previous_path, previous)
        else:
            self.previous_path.unlink(missing_ok=True)
        activation_id = uuid.uuid4().hex
        self._record_operation("activating", version=str(row.get("version") or version), activation_id=activation_id)
        self._record_progress("activating", version=str(row.get("version") or version), activation_id=activation_id, percent=100)
        pointer = {
            "version": str(row.get("version") or version),
            "root": str(root),
            "launcher": launcher,
            "health_path": str(row.get("health_path") or "/api/health"),
            "release_sequence": int(row.get("release_sequence") or 0),
            "release_id": str(row.get("release_id") or ""),
            "activated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "activated_at_epoch": time.time(),
            "activation_id": activation_id,
            "status": "pending_health",
            "human_confirmed": True,
            "health_confirmed": False,
            "automatic_promotion": False,
        }
        self._atomic_json(self.current_path, pointer)
        row["activation_pending"] = True
        row["activation_id"] = activation_id
        row["installed"] = False
        row["health_confirmed"] = False
        row["activated_at"] = pointer["activated_at"]
        self._atomic_json(receipt_path, row)
        return {
            "pointer": pointer,
            "previous_pointer": previous,
            "activation_id": activation_id,
            "launcher_path": str(launcher_path),
            "receipt": row,
            "staged_integrity": integrity,
        }

    def confirm_health(self, version: str, *, activation_id: str | None = None, health: dict[str, Any] | None = None) -> dict[str, Any]:
        pointer = self.current_pointer()
        if not pointer or str(pointer.get("version")) != str(version):
            raise ValueError("No hay una activación pendiente para esa versión")
        if activation_id and str(pointer.get("activation_id")) != str(activation_id):
            raise ValueError("activation_id no coincide")
        root = Path(str(pointer.get("root") or ""))
        receipt_path = root / self.RECEIPT_NAME
        if not receipt_path.is_file():
            raise ValueError("Receipt de actualización no encontrado")
        row = json.loads(receipt_path.read_text(encoding="utf-8"))
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        pointer.update({"status": "healthy", "health_confirmed": True, "health_confirmed_at": now})
        self._atomic_json(self.current_path, pointer)
        row.update({
            "activation_pending": False,
            "installed": True,
            "installed_at": now,
            "health_confirmed": True,
            "health": health or {"ok": True, "version": version},
        })
        self._atomic_json(receipt_path, row)
        self._clear_operation()
        try:
            UpdateFailureEvidenceRecorderV1(self.root).record(
                "healthy", outcome="activation_committed", version=version,
                activation_id=pointer.get("activation_id"), health=health or {},
            )
        except Exception as exc:
            self._note_nonfatal("health.activation_evidence", exc)
        return {"pointer": pointer, "receipt": row}

    def rollback(self, *, reason: str, failed_version: str | None = None) -> dict[str, Any]:
        current = self.current_pointer()
        previous = self.previous_pointer()
        if current and failed_version and str(current.get("version")) != str(failed_version):
            raise ValueError("La versión fallida no coincide con la versión activa")
        if current:
            try:
                root = Path(str(current.get("root") or ""))
                receipt_path = root / self.RECEIPT_NAME
                if receipt_path.is_file():
                    row = json.loads(receipt_path.read_text(encoding="utf-8"))
                    row.update({
                        "activation_pending": False,
                        "installed": False,
                        "health_confirmed": False,
                        "rolled_back": True,
                        "rollback_reason": str(reason)[:1000],
                        "rolled_back_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    })
                    self._atomic_json(receipt_path, row)
            except Exception as exc:
                self._note_nonfatal("rollback.failed_receipt", exc)
        if previous and Path(str(previous.get("root") or "")).is_dir():
            restored = dict(previous)
            restored.update({
                "status": "healthy",
                "rollback_restored_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "rollback_from": str((current or {}).get("version") or failed_version or ""),
                "rollback_reason": str(reason)[:1000],
            })
            self._atomic_json(self.current_path, restored)
            launcher = Path(str(restored["root"])) / str(restored.get("launcher") or "ABRIR_CEO.cmd")
            self._clear_operation()
            result = {"rolled_back": True, "pointer": restored, "launcher_path": str(launcher), "to_bundled_fallback": False}
            try:
                UpdateFailureEvidenceRecorderV1(self.root).record(
                    "rolled_back", outcome="previous_version_restored", reason=reason,
                    failed_version=str((current or {}).get("version") or failed_version or ""),
                    restored_version=str(restored.get("version") or ""), result=result,
                )
            except Exception as exc:
                self._note_nonfatal("rollback.previous_restore_evidence", exc)
            return result
        self.current_path.unlink(missing_ok=True)
        self._clear_operation()
        result = {"rolled_back": True, "pointer": None, "launcher_path": None, "to_bundled_fallback": True}
        try:
            UpdateFailureEvidenceRecorderV1(self.root).record(
                "rolled_back", outcome="bundled_fallback_required", reason=reason,
                failed_version=str((current or {}).get("version") or failed_version or ""), result=result,
            )
        except Exception as exc:
            self._note_nonfatal("rollback.bundled_fallback_evidence", exc)
        return result

    def verify_health_url(
        self,
        url: str,
        *,
        expected_version: str,
        activation_id: str | None = None,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        req = urllib.request.Request(url, headers={"User-Agent": "CEO-de-IAs-Update-Health/1"})
        with self._urlopen(req, timeout=timeout) as resp:
            raw = resp.read(1024 * 1024)
            status = int(getattr(resp, "status", 200) or 200)
        if status < 200 or status >= 300:
            raise RuntimeError(f"Health endpoint HTTP {status}")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise RuntimeError("Health endpoint no confirmó ok=true")
        if str(payload.get("version") or "") != str(expected_version):
            raise RuntimeError("Health endpoint pertenece a otra versión")
        if activation_id and str(payload.get("activation_id") or "") != str(activation_id):
            raise RuntimeError("Health endpoint activation_id no coincide")
        return payload
