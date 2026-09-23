from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(os.environ["CEO_W11_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))
os.environ["CEO_W9_ROOT"] = str(ROOT)

from ceo_core.deliverable_evidence_engine_v1 import DeliverableEvidenceEngineV1
from ceo_core.goal_lock_local_provider_v1 import GoalLockLocalProviderV1
from ceo_core.graph import TaskGraph
from ceo_core.local_finite_file_provider_v1 import LocalFiniteFileProviderV1
from ceo_core.models import ProjectState, TaskStatus
from ceo_core.routing import MultiProviderRouter
from ceo_core.scheduler import ContinuousScheduler, FilesystemOperations

W9_PATH = pathlib.Path(__file__).resolve().with_name("w9_local_finite_regression.py")
spec = importlib.util.spec_from_file_location("ceo_w9_regression_w11", W9_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load W9 helpers")
w9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w9)

EXPECTED = w9.EXPECTED
TARGET = "CEO_LOCAL_W9.txt"


class PauseBeforeFirstWrite(LocalFiniteFileProviderV1):
    def __init__(self):
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, request):
        mode = str(request.work_unit.metadata.get("local_finite_file_mode") or "")
        if mode == "write" and not self.entered.is_set():
            self.entered.set()
            await self.release.wait()
        return await super().execute(request)


async def wait_done(state: ProjectState, timeout: float = 25.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state.completed_at is not None:
            return
        bad = [t for t in state.leaf_tasks if t.status in {TaskStatus.FAILED, TaskStatus.NEEDS_REVIEW}]
        if bad:
            raise AssertionError([
                {"id": t.id, "title": t.title, "status": t.status.value, "result": t.result}
                for t in bad
            ])
        await asyncio.sleep(0.05)
    raise AssertionError("W11 scheduler completion timeout")


def execution_task(state: ProjectState):
    rows=[t for t in state.leaf_tasks if str(t.title or "").lower().startswith("execution")]
    assert len(rows)==1, [(t.id,t.title,t.status.value) for t in state.leaf_tasks]
    return rows[0]


async def build_effect_and_stale_checkpoint(workspace: pathlib.Path, state_dir: pathlib.Path):
    state=w9.prepare_state(workspace)
    initial_ids={t.id for t in state.leaf_tasks}
    ex=execution_task(state)
    store=w9.JsonCheckpointStore(state_dir/"live.json")
    store.save(state)
    pausing=PauseBeforeFirstWrite()
    scheduler=ContinuousScheduler(
        state,None,store,graph=TaskGraph(),
        router=MultiProviderRouter([GoalLockLocalProviderV1(),pausing]),
    )
    scheduler.start()
    await asyncio.wait_for(pausing.entered.wait(),timeout=10.0)
    assert ex.status==TaskStatus.RUNNING, ex.status
    stale_blob=state.model_dump_json()
    pausing.release.set()
    await wait_done(state)
    await scheduler.stop()
    target=workspace/TARGET
    assert target.read_text(encoding="utf-8")==EXPECTED
    return stale_blob, initial_ids, hashlib.sha256(target.read_bytes()).hexdigest()


async def replay_from_stale(stale_blob: str, workspace: pathlib.Path, state_dir: pathlib.Path):
    state=ProjectState.model_validate_json(stale_blob)
    store=w9.JsonCheckpointStore(state_dir/"replay.json")
    store.save(state)

    physical=[]
    original=FilesystemOperations.write_text

    def tracked(self, relative, content):
        physical.append({"path":str(relative),"content":str(content)})
        return original(self,relative,content)

    FilesystemOperations.write_text=tracked
    try:
        scheduler=ContinuousScheduler(
            state,None,store,graph=TaskGraph(),
            router=MultiProviderRouter([GoalLockLocalProviderV1(),LocalFiniteFileProviderV1()]),
        )
        scheduler.start()
        await wait_done(state)
        await scheduler.stop()
    finally:
        FilesystemOperations.write_text=original
    return state, physical


async def main_async():
    raw_mode=os.environ.get("CEO_W11_EXPECT_RAW_BUG")=="1"

    with tempfile.TemporaryDirectory(prefix="ceo-w11-ws-") as ws_raw, tempfile.TemporaryDirectory(prefix="ceo-w11-state-") as st_raw:
        workspace=pathlib.Path(ws_raw).resolve()
        state_dir=pathlib.Path(st_raw).resolve()
        stale_blob,initial_ids,first_sha=await build_effect_and_stale_checkpoint(workspace,state_dir)
        target=workspace/TARGET
        fixed_ns=1_600_000_000_000_000_000
        os.utime(target,ns=(fixed_ns,fixed_ns))
        before_ns=target.stat().st_mtime_ns

        replayed,writes=await replay_from_stale(stale_blob,workspace,state_dir)
        after_ns=target.stat().st_mtime_ns
        ex=execution_task(replayed)
        final_sha=hashlib.sha256(target.read_bytes()).hexdigest()

        row={
            "physical_writes":len(writes),
            "physical_write_payloads":writes,
            "mtime_changed":after_ns!=before_ns,
            "same_sha":first_sha==final_sha,
            "same_leaf_ids":{t.id for t in replayed.leaf_tasks}==initial_ids,
            "completed_at":str(replayed.completed_at),
            "execution_attempts":ex.attempts,
            "workspace_writes":ex.metadata.get("workspace_writes_v1"),
            "idempotent_noops":ex.metadata.get("workspace_idempotent_noops_v1"),
        }
        print("W11_STALE_REPLAY",json.dumps(row,ensure_ascii=False,default=str,sort_keys=True))

        if raw_mode:
            assert len(writes)>0, "Raw candidate unexpectedly avoided duplicate physical writes"
            print("W11_RAW_DUPLICATE_SIDE_EFFECT_REPRODUCED")
            return {"raw_bug_reproduced":True,"row":row}

        assert len(writes)==0, row
        assert after_ns==before_ns, row
        assert first_sha==final_sha, row
        assert replayed.completed_at is not None
        assert row["same_leaf_ids"] is True
        assert int(ex.metadata.get("workspace_idempotent_noops_v1",0))>=1, ex.metadata
        assert all(x.get("physical_write") is False for x in (ex.metadata.get("workspace_writes_v1") or [])), ex.metadata

        # Same-state evidence replay must not inflate durable evidence rows.
        engine=DeliverableEvidenceEngineV1()
        rows=replayed.metadata.setdefault(engine.KEY,[])
        same_before=[
            x for x in rows
            if isinstance(x,dict)
            and x.get("task_id")==ex.id
            and x.get("kind")=="file"
            and x.get("sha256")==final_sha
        ]
        engine.record_file(replayed,ex,target,root=workspace)
        engine.record_file(replayed,ex,target,root=workspace)
        same_after=[
            x for x in replayed.metadata.get(engine.KEY,[])
            if isinstance(x,dict)
            and x.get("task_id")==ex.id
            and x.get("kind")=="file"
            and x.get("sha256")==final_sha
        ]
        assert len(same_after)==max(1,len(same_before)), {
            "before":same_before,"after":same_after
        }

        # If the existing side effect is wrong, replay must repair it rather
        # than treating it as an idempotent success.
        target.write_text("BROKEN_W11",encoding="utf-8")
        corrupted=ProjectState.model_validate_json(stale_blob)
        corrupt_store=w9.JsonCheckpointStore(state_dir/"corrupt.json")
        corrupt_store.save(corrupted)
        repair_writes=[]
        original=FilesystemOperations.write_text
        def tracked_repair(self,relative,content):
            repair_writes.append({"path":str(relative),"content":str(content)})
            return original(self,relative,content)
        FilesystemOperations.write_text=tracked_repair
        try:
            scheduler=ContinuousScheduler(
                corrupted,None,corrupt_store,graph=TaskGraph(),
                router=MultiProviderRouter([GoalLockLocalProviderV1(),LocalFiniteFileProviderV1()]),
            )
            scheduler.start()
            await wait_done(corrupted)
            await scheduler.stop()
        finally:
            FilesystemOperations.write_text=original
        assert repair_writes, "Corrupted target was not repaired"
        assert target.read_text(encoding="utf-8")==EXPECTED
        assert corrupted.completed_at is not None
        print("W11_CORRUPT_REPAIR",json.dumps({
            "physical_writes":len(repair_writes),
            "final_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
            "completed_at":str(corrupted.completed_at),
        },sort_keys=True))
        return {"raw_bug_reproduced":False,"row":row,"repair_writes":len(repair_writes)}


def package_hash(relative: str):
    contract=json.loads((ROOT/"CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
    expected=str((contract.get("file_hashes") or {}).get(relative) or "")
    actual=hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
    assert expected and expected==actual,(relative,expected,actual)
    return actual


def main():
    result=asyncio.run(main_async())
    if os.environ.get("CEO_W11_EXPECT_RAW_BUG")=="1":
        return 0
    hashes={
        rel:package_hash(rel)
        for rel in (
            "ceo_core/local_finite_file_provider_v1.py",
            "ceo_core/scheduler.py",
            "ceo_core/deliverable_evidence_engine_v1.py",
        )
    }
    print("W11_PACKAGE_HASHES",json.dumps(hashes,sort_keys=True))
    print("W11_LOCAL_IDEMPOTENCY_REGRESSION_PASS")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
