from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .internal_release_publisher import InternalReleasePublisher, InternalReleasePublishResult
from .runtime import user_data_root


@dataclass(slots=True)
class InternalReleaseRequest:
    package_path: str
    version: str
    release_sequence: int
    release_id: str
    notes: str
    min_app_version: str
    qualification: dict[str, Any]
    created_at: str = ""


class InternalReleaseCoordinator:
    """Zero-touch publication coordinator for CEO's own update channel.

    It never installs a build. Installation remains an explicit operator action in
    the in-app updater.  This coordinator only accepts locally qualified CEO update
    packages and delegates signing/publication to InternalReleasePublisher, whose
    scope is hard-limited to the built-in CEO update channel.

    Requests are durable so a validated self-development run can enqueue a release
    even if the publisher is temporarily unavailable.  A background watcher may
    retry only transient publication/authentication failures; it never weakens a
    failed qualification or signature gate.
    """

    REQUIRED_QUALIFICATION_FLAGS = (
        "tests_passed",
        "clean_extract_passed",
        "package_contract_passed",
        "security_passed",
    )
    TERMINAL_FAILURES = {
        "ANTI_REPLAY_BLOCKED",
        "COMMIT_FAILED",
        "REMOTE_VERIFY_FAILED",
        "REMOTE_PACKAGE_VERIFY_FAILED",
        "QUALIFICATION_REJECTED",
        "INVALID_REQUEST",
        "UNCLASSIFIED_FAILURE",
    }
    RETRYABLE_FAILURES = {
        "SIGNER_UNAVAILABLE",
        "CHANNEL_READ_FAILED",
        "PUBLICATION_AUTH_OR_PUSH_FAILED",
    }

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        publisher: InternalReleasePublisher | None = None,
        poll_seconds: float = 30.0,
    ) -> None:
        self.root = Path(root) if root else user_data_root() / "updates" / "internal-release"
        self.queue_dir = self.root / "queue"
        self.receipt_dir = self.root / "receipts"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.receipt_dir.mkdir(parents=True, exist_ok=True)
        self.publisher = publisher or InternalReleasePublisher()
        self.poll_seconds = max(5.0, float(poll_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    @classmethod
    def validate_qualification(cls, payload: dict[str, Any]) -> tuple[bool, list[str]]:
        q = payload if isinstance(payload, dict) else {}
        problems: list[str] = []
        for key in cls.REQUIRED_QUALIFICATION_FLAGS:
            if q.get(key) is not True:
                problems.append(f"{key}=false")
        if int(q.get("failed_tests") or 0) != 0:
            problems.append("failed_tests>0")
        if int(q.get("security_findings") or 0) != 0:
            problems.append("security_findings>0")
        # A candidate may explicitly carry local_candidate_ready as an additional
        # aggregate gate. If present it must be true; absence remains compatible
        # with older qualification producers that provide the four concrete gates.
        if "local_candidate_ready" in q and q.get("local_candidate_ready") is not True:
            problems.append("local_candidate_ready=false")
        return not problems, problems

    def enqueue(self, request: InternalReleaseRequest) -> dict[str, Any]:
        ok, problems = self.validate_qualification(request.qualification)
        if not ok:
            return {
                "ok": False,
                "status": "QUALIFICATION_REJECTED",
                "version": request.version,
                "problems": problems,
                "automatic_installation": False,
            }
        if int(request.release_sequence) <= 0 or not str(request.version).strip():
            return {"ok": False, "status": "INVALID_REQUEST", "version": request.version, "automatic_installation": False}
        package = Path(request.package_path).resolve()
        if not package.is_file():
            return {"ok": False, "status": "INVALID_REQUEST", "version": request.version, "detail": "package not found", "automatic_installation": False}
        payload = asdict(request)
        payload["package_path"] = str(package)
        payload["created_at"] = request.created_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        payload["attempts"] = 0
        payload["last_status"] = "QUEUED"
        payload["next_retry_at"] = 0.0
        path = self.queue_dir / f"{int(request.release_sequence):06d}-{request.version}.json"
        self._atomic_json(path, payload)
        return {"ok": True, "status": "QUEUED", "queue_file": str(path), "version": request.version, "automatic_installation": False}

    def _receipt(self, request_path: Path, request: dict[str, Any], result: InternalReleasePublishResult | dict[str, Any]) -> dict[str, Any]:
        row = asdict(result) if isinstance(result, InternalReleasePublishResult) else dict(result)
        payload = {
            "request": {k: v for k, v in request.items() if k != "qualification"},
            "qualification": dict(request.get("qualification") or {}),
            "result": row,
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "automatic_installation": False,
            "operator_install_confirmation_required": True,
        }
        out = self.receipt_dir / request_path.name
        self._atomic_json(out, payload)
        return payload

    def _process_path(self, path: Path) -> dict[str, Any]:
        request = json.loads(path.read_text(encoding="utf-8"))
        ok, problems = self.validate_qualification(request.get("qualification") or {})
        if not ok:
            result = {"ok": False, "status": "QUALIFICATION_REJECTED", "version": request.get("version", ""), "problems": problems}
            self._receipt(path, request, result)
            path.unlink(missing_ok=True)
            return result
        result = self.publisher.publish(
            package_path=request["package_path"],
            version=request["version"],
            release_sequence=int(request["release_sequence"]),
            release_id=request["release_id"],
            notes=request.get("notes", ""),
            min_app_version=request.get("min_app_version", ""),
        )
        self._receipt(path, request, result)
        if result.ok or result.status in self.TERMINAL_FAILURES:
            path.unlink(missing_ok=True)
            return asdict(result)
        request["attempts"] = int(request.get("attempts") or 0) + 1
        request["last_status"] = result.status
        request["last_detail"] = result.detail
        if result.status == "PUBLICATION_AUTH_OR_PUSH_FAILED" and request["attempts"] >= 2:
            request["suspended"] = True
            request["attention_code"] = "GITHUB_UPDATE_CHANNEL_AUTH_REQUIRED"
            request["next_retry_at"] = 0.0
            self._atomic_json(path, request)
            return asdict(result)
        if result.status in self.RETRYABLE_FAILURES and request["attempts"] < 4:
            request["next_retry_at"] = time.time() + min(3600.0, 60.0 * (2 ** min(request["attempts"], 5)))
            self._atomic_json(path, request)
            return asdict(result)
        request["terminal_reason"] = "retry_budget_exhausted_or_unclassified"
        self._atomic_json(path, request)
        self._receipt(path, request, {"ok":False,"status":"UNCLASSIFIED_FAILURE","version":request.get("version", ""),"detail":request.get("last_detail", "")})
        path.unlink(missing_ok=True)
        return asdict(result)

    def scan_once(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not self._lock.acquire(blocking=False):
            return rows
        try:
            now = time.time()
            for path in sorted(self.queue_dir.glob("*.json")):
                try:
                    request = json.loads(path.read_text(encoding="utf-8"))
                    if request.get("suspended"):
                        continue
                    if float(request.get("next_retry_at") or 0.0) > now:
                        continue
                    rows.append(self._process_path(path))
                except Exception as exc:
                    rows.append({"ok": False, "status": "COORDINATOR_ERROR", "detail": f"{type(exc).__name__}: {exc}"[:800], "request": path.name})
            return rows
        finally:
            self._lock.release()

    def status(self) -> dict[str, Any]:
        queued = []
        for path in sorted(self.queue_dir.glob("*.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                queued.append({
                    "version": row.get("version"),
                    "release_sequence": row.get("release_sequence"),
                    "attempts": row.get("attempts", 0),
                    "last_status": row.get("last_status", "QUEUED"),
                    "next_retry_at": row.get("next_retry_at", 0),
                    "suspended": bool(row.get("suspended")),
                    "attention_code": row.get("attention_code"),
                })
            except Exception:
                queued.append({"request": path.name, "last_status": "UNREADABLE"})
        receipts = sorted(self.receipt_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        latest = None
        if receipts:
            try:
                latest = json.loads(receipts[0].read_text(encoding="utf-8"))
            except Exception:
                latest = {"status": "UNREADABLE_RECEIPT"}
        latest_result=(latest or {}).get("result") if isinstance(latest,dict) else None
        latest_status=str((latest_result or {}).get("status") or "")
        attention=next((x for x in queued if x.get("suspended") and x.get("attention_code")),None)
        publication_state="published" if latest_status=="PUBLISHED" else "attention_required" if attention else "queued" if queued else "idle"
        return {
            "enabled": True,
            "queued": queued,
            "latest": latest,
            "publication_state": publication_state,
            "operator_attention_required": bool(attention),
            "attention_code": (attention or {}).get("attention_code"),
            "published_version": (latest_result or {}).get("version") if latest_status=="PUBLISHED" else None,
            "published_release_sequence": (latest_result or {}).get("release_sequence") if latest_status=="PUBLISHED" else None,
            "published_commit": (latest_result or {}).get("commit") if latest_status=="PUBLISHED" else None,
            "automatic_publication_scope": "ceo-own-update-channel-only",
            "automatic_installation": False,
            "operator_install_confirmation_required": True,
        }

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        def _run() -> None:
            while not self._stop.wait(self.poll_seconds):
                try:
                    self.scan_once()
                except Exception:
                    pass
        self._thread = threading.Thread(target=_run, name="ceo-internal-release", daemon=True)
        self._thread.start()
        # Do one immediate pass without blocking CEO startup on network work.
        threading.Thread(target=self.scan_once, name="ceo-internal-release-initial", daemon=True).start()
        return True

    def stop(self) -> None:
        self._stop.set()
