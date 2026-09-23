from __future__ import annotations

import hashlib
import json
import os
import pathlib


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def patch_local_provider(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = """        if mode == "write":
            footer = self._footer(
                {
                    "status": "complete",
                    "reason": "bounded local file write completed",
                    "confidence": 1.0,
                    "requires_user": False,
                    "evidence_refs": [],
                    "write_files": [
                        {"path": relative_path, "content": "[CEO_LOCAL_DRAFT]\\n"},
                        {"path": relative_path, "content": content},
                    ],
                }
            )
"""
    new = """        if mode == "write":
            # W11: replay after a crash can re-enter the same task after the
            # filesystem effect already happened but before COMPLETE was
            # checkpointed. If the exact intended bytes are already present,
            # never transiently replace them with the draft again.
            already_exact = False
            try:
                already_exact = target.is_file() and target.read_text(encoding="utf-8") == content
            except Exception:
                already_exact = False
            writes = (
                [{"path": relative_path, "content": content}]
                if already_exact
                else [
                    {"path": relative_path, "content": "[CEO_LOCAL_DRAFT]\\n"},
                    {"path": relative_path, "content": content},
                ]
            )
            footer = self._footer(
                {
                    "status": "complete",
                    "reason": (
                        "bounded local file replay converged on existing exact content"
                        if already_exact
                        else "bounded local file write completed"
                    ),
                    "confidence": 1.0,
                    "requires_user": False,
                    "evidence_refs": [],
                    "write_files": writes,
                }
            )
"""
    text = replace_once(text, old, new, "W11 provider replay detection")
    old2 = '''                metadata={
                    "local_finite_file": True,
                    "mode": "write",
                    "network_used": False,
                    "shell_used": False,
                    "spending_attempts": 0,
                },
'''
    new2 = '''                metadata={
                    "local_finite_file": True,
                    "mode": "write",
                    "idempotent_replay_candidate": bool(already_exact),
                    "network_used": False,
                    "shell_used": False,
                    "spending_attempts": 0,
                },
'''
    text = replace_once(text, old2, new2, "W11 provider metadata")
    path.write_text(text, encoding="utf-8")


def patch_scheduler(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import pathlib\nimport re\n",
        "import hashlib\nimport pathlib\nimport re\n",
        "W11 scheduler hashlib import",
    )
    old = """                            row = fs.write_text(relative, str(spec.content))
                            verified = exchange.register(
"""
    new = """                            desired_content = str(spec.content)
                            candidate = (pathlib.Path(workspace_root) / relative).resolve()
                            try:
                                candidate.relative_to(pathlib.Path(workspace_root).resolve())
                            except ValueError as exc:
                                raise PermissionError("workspace write escaped managed root") from exc

                            # W11: exact-content replay is a durable no-op. We
                            # still register artifact/evidence below so a stale
                            # checkpoint can reconstruct proof without repeating
                            # the physical side effect.
                            idempotent_noop = False
                            if candidate.is_file():
                                try:
                                    idempotent_noop = candidate.read_text(encoding="utf-8") == desired_content
                                except Exception:
                                    idempotent_noop = False
                            if idempotent_noop:
                                payload = candidate.read_bytes()
                                row = {
                                    "sha256": hashlib.sha256(payload).hexdigest(),
                                    "size_bytes": len(payload),
                                    "idempotent_noop": True,
                                    "physical_write": False,
                                }
                            else:
                                row = fs.write_text(relative, desired_content)
                                row["idempotent_noop"] = False
                                row["physical_write"] = True
                            verified = exchange.register(
"""
    text = replace_once(text, old, new, "W11 scheduler idempotent write")
    old_written = """                            written.append({
                                "path": relative,
                                "sha256": row.get("sha256"),
                                "size_bytes": row.get("size_bytes"),
                                "artifact_id": verified.get("artifact_id"),
                                "evidence_ref": evidence.ref,
                            })
"""
    new_written = """                            written.append({
                                "path": relative,
                                "sha256": row.get("sha256"),
                                "size_bytes": row.get("size_bytes"),
                                "artifact_id": verified.get("artifact_id"),
                                "evidence_ref": evidence.ref,
                                "idempotent_noop": bool(row.get("idempotent_noop", False)),
                                "physical_write": bool(row.get("physical_write", True)),
                            })
"""
    text = replace_once(text, old_written, new_written, "W11 write audit metadata")
    old2 = """                            task.metadata.setdefault("verified_artifacts", []).extend(
                                x["artifact_id"] for x in written if x.get("artifact_id")
                            )
                            task.metadata["workspace_writes_v1"] = written
"""
    new2 = """                            verified_artifacts = task.metadata.setdefault("verified_artifacts", [])
                            for artifact_id in (x["artifact_id"] for x in written if x.get("artifact_id")):
                                if artifact_id not in verified_artifacts:
                                    verified_artifacts.append(artifact_id)
                            task.metadata["workspace_writes_v1"] = written
                            task.metadata["workspace_idempotent_noops_v1"] = sum(
                                1 for row in written if row.get("idempotent_noop")
                            )
"""
    text = replace_once(text, old2, new2, "W11 verified artifact de-dup")
    path.write_text(text, encoding="utf-8")


def patch_evidence(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = """    def _append(self, state: ProjectState, task: Task, record: EvidenceRecord) -> None:
        rows = state.metadata.setdefault(self.KEY, [])
        rows.append(record.to_dict())
        del rows[:-5000]
        refs = task.metadata.setdefault("evidence_refs", [])
"""
    new = """    def _append(self, state: ProjectState, task: Task, record: EvidenceRecord) -> None:
        rows = state.metadata.setdefault(self.KEY, [])
        payload = record.to_dict()

        # W11: repeated observation of the same task/file/content after a
        # replay reconstructs proof; it must not inflate the evidence ledger.
        duplicate = any(
            isinstance(row, dict)
            and str(row.get("task_id") or "") == record.task_id
            and str(row.get("kind") or "") == record.kind
            and str(row.get("ref") or "") == record.ref
            and str(row.get("sha256") or "") == record.sha256
            for row in rows
        )
        if not duplicate:
            rows.append(payload)
            del rows[:-5000]
        refs = task.metadata.setdefault("evidence_refs", [])
"""
    text = replace_once(text, old, new, "W11 evidence de-dup")
    path.write_text(text, encoding="utf-8")


def apply(root: pathlib.Path) -> dict:
    root = root.resolve()
    targets = {
        "ceo_core/local_finite_file_provider_v1.py": patch_local_provider,
        "ceo_core/scheduler.py": patch_scheduler,
        "ceo_core/deliverable_evidence_engine_v1.py": patch_evidence,
    }
    hashes = {}
    for relative, fn in targets.items():
        path = root / relative
        fn(path)
        hashes[relative] = sha256_file(path)

    contract_path = root / "CEO_UPDATE_PACKAGE.json"
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        file_hashes = dict(contract.get("file_hashes") or {})
        required = contract.get("required_files")
        for relative, digest in hashes.items():
            file_hashes[relative] = digest
            if isinstance(required, list) and relative not in required:
                required.append(relative)
        contract["file_hashes"] = file_hashes
        contract_path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return {"ok": True, "hashes": hashes}


def main() -> int:
    raw = str(os.environ.get("CEO_W11_ROOT") or "").strip()
    if not raw:
        raise RuntimeError("CEO_W11_ROOT is required")
    row = apply(pathlib.Path(raw))
    print("W11_LOCAL_IDEMPOTENCY_FIX_APPLIED")
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
