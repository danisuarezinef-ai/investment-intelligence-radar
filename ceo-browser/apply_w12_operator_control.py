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


def patch_work_mode(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = '''    async def pause(self, paused: bool):
        state = self._state_obj()
        if state is None:
            return await self.snapshot()
        state.paused = bool(paused)
        if paused:
            state.metadata["operator_paused_v1"] = True
            state.metadata["operator_paused_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            state.metadata.pop("operator_paused_v1", None)
            state.metadata.pop("operator_paused_at", None)
        if self.scheduler is not None:
            self.scheduler.store.save(state)
        else:
            self.projects.store(state.id).save(state)
        self.projects.touch(state)
        return await self.snapshot()
'''
    new = '''    async def pause(self, paused: bool):
        state = self._state_obj()
        if state is None:
            return await self.snapshot()

        if paused:
            # W12: an operator pause is a durable execution boundary, not merely
            # a dispatch flag. Persist the intent first, then quiesce/cancel any
            # in-flight worker through the existing restart-safe stop path.
            state.paused = True
            state.metadata["operator_paused_v1"] = True
            state.metadata["operator_paused_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            state.metadata["operator_productivity_state"] = "PAUSADO"
            store = self.scheduler.store if self.scheduler is not None else self.projects.store(state.id)
            store.save(state)
            self.projects.touch(state)

            stop_report = await self._stop_scheduler(timeout_seconds=4.0)
            state = self._state_obj() or state
            state.paused = True
            state.metadata["operator_paused_v1"] = True
            state.metadata["operator_pause_quiesce_v1"] = {
                "ok": bool(stop_report.get("ok", True)),
                "mode": str(stop_report.get("mode") or "unknown"),
                "forced": bool(stop_report.get("forced", False)),
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            durable_store = self.projects.store(state.id)
            durable_store.save(state)
            self.projects.touch(state)
            return await self.snapshot()

        if state.cancelled_at is not None or state.metadata.get("operator_cancelled"):
            raise RuntimeError(
                "Este proyecto fue cancelado y no puede reanudarse. "
                "Crea un nuevo objetivo si quieres retomarlo."
            )

        # W12: after an app restart, a deliberately paused project has no live
        # scheduler. Reanudar must recreate execution, not only flip the flag.
        state.paused = False
        state.metadata.pop("operator_paused_v1", None)
        state.metadata.pop("operator_paused_at", None)
        state.metadata["operator_resumed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        state.metadata["operator_productivity_state"] = "REANUDADO"
        store = self.projects.store(state.id)
        store.save(state)
        self.projects.touch(state)

        if self.scheduler is None and state.completed_at is None:
            self.router = self._router()
            self.scheduler = self.ContinuousScheduler(
                state, None, store, graph=self.Graph(), router=self.router
            )
            self.scheduler.start()
        return await self.snapshot()
'''
    text = replace_once(text, old, new, "W12 pause/resume lifecycle")
    path.write_text(text, encoding="utf-8")


def apply(root: pathlib.Path) -> dict:
    root = root.resolve()
    relative = "scripts/ceo_stdlib_work_mode.py"
    path = root / relative
    patch_work_mode(path)
    digest = sha256_file(path)

    contract_path = root / "CEO_UPDATE_PACKAGE.json"
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        hashes = dict(contract.get("file_hashes") or {})
        hashes[relative] = digest
        contract["file_hashes"] = hashes
        required = contract.get("required_files")
        if isinstance(required, list) and relative not in required:
            required.append(relative)
        contract_path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return {"ok": True, "patched": relative, "sha256": digest, "contract_hash_updated": True}


def main() -> int:
    raw = str(os.environ.get("CEO_W12_ROOT") or "").strip()
    if not raw:
        raise RuntimeError("CEO_W12_ROOT is required")
    row = apply(pathlib.Path(raw))
    print("W12_OPERATOR_CONTROL_FIX_APPLIED")
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
