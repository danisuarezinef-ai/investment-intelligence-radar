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


def apply(root: pathlib.Path) -> dict:
    root = root.resolve()
    path = root / "ceo_core" / "operational_resilience.py"
    text = path.read_text(encoding="utf-8")

    old = """                    task.metadata["retry_after_ts"] = 0
                    task.worker_id = None
                    report.recovered_running += 1
"""
    new = """                    task.metadata["retry_after_ts"] = 0

                    # W10: the worker process/session that owned this RUNNING
                    # checkpoint no longer exists. The task can only be safely
                    # retried if its durable worker lease is released at the
                    # same boundary. Otherwise WorkerLifecycleV2.claim() sees
                    # the still-unexpired lease and blocks the recovered task
                    # for the remainder of the old TTL.
                    lease_rows = state.metadata.get("worker_leases_v2")
                    if isinstance(lease_rows, dict):
                        lease_row = lease_rows.get(task.id)
                        if isinstance(lease_row, dict) and not lease_row.get("released"):
                            lease_row["released"] = True
                            lease_row["release_reason"] = "restart_interrupted_worker"
                            lease_row["released_at"] = now
                    task_lease = task.metadata.get("worker_lease_v2")
                    if isinstance(task_lease, dict) and not task_lease.get("released"):
                        task_lease["released"] = True
                        task_lease["release_reason"] = "restart_interrupted_worker"
                        task_lease["released_at"] = now
                    task.metadata["worker_lease_recovered_v2"] = True
                    task.metadata.pop("worker_lease_collision_v2", None)
                    task.worker_id = None
                    report.recovered_running += 1
"""
    text = replace_once(text, old, new, "W10 resume lease release")
    path.write_text(text, encoding="utf-8")

    contract_path = root / "CEO_UPDATE_PACKAGE.json"
    updated = False
    rel = "ceo_core/operational_resilience.py"
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        hashes = dict(contract.get("file_hashes") or {})
        hashes[rel] = sha256_file(path)
        contract["file_hashes"] = hashes
        required = contract.get("required_files")
        if isinstance(required, list) and rel not in required:
            required.append(rel)
        contract_path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        updated = True

    return {
        "ok": True,
        "patched": rel,
        "sha256": sha256_file(path),
        "contract_hash_updated": updated,
    }


def main() -> int:
    raw = str(os.environ.get("CEO_W10_ROOT") or "").strip()
    if not raw:
        raise RuntimeError("CEO_W10_ROOT is required")
    row = apply(pathlib.Path(raw))
    print("W10_RESTART_LEASE_FIX_APPLIED")
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
