from __future__ import annotations

import json
import sqlite3
import zlib
from hashlib import blake2b
from pathlib import Path
from threading import RLock

from .migrations import migrate_state
from .continuity import ContinuityManager
from .models import Decision, ProjectState, Task, TaskStatus
from .operational_resilience import ResumeCoordinator
from .store import CheckpointStore


class SqliteCheckpointStore(CheckpointStore):
    """Incremental local persistence for large projects.

    Project metadata is one row; task/decision rows are updated only when their compact
    signatures change. SQLite is built into Python and requires no extra Windows service.
    """
    def __init__(self, path: str | Path = "data/ceo.db") -> None:
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self._lock=RLock();self._task_sigs={};self._decision_sigs={};self._continuity_digest=None;self.continuity=ContinuityManager()
        with self._connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS project(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots(seq INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, project_payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS full_snapshots(seq INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, payload BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS continuity_history(seq INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, digest TEXT NOT NULL, payload TEXT NOT NULL);
            ''')

    def _connect(self): return sqlite3.connect(self.path,timeout=30)
    @staticmethod
    def _sig_task(t: Task) -> str:
        compact=f"{t.status}|{t.attempts}|{t.conversation_turns}|{t.result}|{t.children}|{t.dependencies}|{t.metadata}|{t.quality_score}|{t.confidence}"
        return blake2b(compact.encode(),digest_size=12).hexdigest()
    @staticmethod
    def _sig_decision(d: Decision) -> str:
        return blake2b(d.model_dump_json().encode(),digest_size=12).hexdigest()

    def save(self,state:ProjectState)->None:
        """Persist one complete state transition atomically.

        Important invariant: in-memory signatures are advanced only *after* SQLite
        commits.  Older builds updated the signature cache while the transaction was
        still open; a process kill/exception could therefore make a later save think
        an uncommitted task was already durable.  BEGIN IMMEDIATE + post-commit cache
        publication makes checkpointing crash-safe and repeatable.
        """
        continuity = self.continuity.capture(state, reason="checkpoint")
        next_task_sigs = dict(self._task_sigs)
        next_decision_sigs = dict(self._decision_sigs)
        next_continuity_digest = self._continuity_digest
        with self._lock:
            c = self._connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                if continuity.get("digest") != self._continuity_digest:
                    digest = str(continuity.get("digest"))
                    c.execute(
                        "INSERT INTO continuity_history(digest,payload) VALUES(?,?)",
                        (digest, json.dumps(continuity, ensure_ascii=False, default=str)),
                    )
                    c.execute("DELETE FROM continuity_history WHERE seq NOT IN (SELECT seq FROM continuity_history ORDER BY seq DESC LIMIT 250)")
                    next_continuity_digest = digest
                project=state.model_dump(mode='json',exclude={'tasks','decisions'})
                project.setdefault('metadata', {})['durable_checkpoint_v1'] = {
                    'task_count': len(state.tasks),
                    'decision_count': len(state.decisions),
                    'continuity_digest': next_continuity_digest,
                }
                payload=json.dumps(project,ensure_ascii=False,default=str,separators=(',',':'))
                c.execute('INSERT INTO project(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(state.id,payload))
                c.execute('DELETE FROM project WHERE id<>?', (state.id,))

                changed=[]
                for t in state.tasks.values():
                    sig=self._sig_task(t)
                    if self._task_sigs.get(t.id)!=sig:
                        changed.append((t.id,t.model_dump_json()))
                    next_task_sigs[t.id]=sig
                if changed:
                    c.executemany('INSERT INTO tasks(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',changed)

                changed_d=[]
                for d in state.decisions.values():
                    sig=self._sig_decision(d)
                    if self._decision_sigs.get(d.id)!=sig:
                        changed_d.append((d.id,d.model_dump_json()))
                    next_decision_sigs[d.id]=sig
                if changed_d:
                    c.executemany('INSERT INTO decisions(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',changed_d)

                ids=set(state.tasks)
                dbids={r[0] for r in c.execute('SELECT id FROM tasks')}
                if dbids-ids:c.executemany('DELETE FROM tasks WHERE id=?',[(x,) for x in dbids-ids])
                dids=set(state.decisions);dbd={r[0] for r in c.execute('SELECT id FROM decisions')}
                if dbd-dids:c.executemany('DELETE FROM decisions WHERE id=?',[(x,) for x in dbd-dids])

                c.commit()
            except Exception:
                c.rollback()
                raise
            finally:
                c.close()

            # Publish caches only after durable commit.
            self._task_sigs = {k:v for k,v in next_task_sigs.items() if k in state.tasks}
            self._decision_sigs = {k:v for k,v in next_decision_sigs.items() if k in state.decisions}
            self._continuity_digest = next_continuity_digest

    def load(self)->ProjectState|None:
        with self._lock,self._connect() as c:
            # Per-project databases created by ProjectCatalog live under a directory
            # whose basename is the canonical project id. Prefer that row explicitly
            # instead of whichever row happened to be inserted most recently. This is
            # backward-compatible with generic stores: if no matching id exists, fall
            # back to the latest row as before.
            preferred_id = self.path.parent.name
            row=c.execute('SELECT payload FROM project WHERE id=? LIMIT 1',(preferred_id,)).fetchone()
            if row is None:
                row=c.execute('SELECT payload FROM project ORDER BY rowid DESC LIMIT 1').fetchone()
            if not row:return None
            data=json.loads(row[0]); tasks={}; decisions={}
            for tid,payload in c.execute('SELECT id,payload FROM tasks'):
                t=Task.model_validate_json(payload);tasks[tid]=t;self._task_sigs[tid]=self._sig_task(t)
            for did,payload in c.execute('SELECT id,payload FROM decisions'):
                d=Decision.model_validate_json(payload);decisions[did]=d;self._decision_sigs[did]=self._sig_decision(d)
            data['tasks']={k:v.model_dump(mode='json') for k,v in tasks.items()};data['decisions']={k:v.model_dump(mode='json') for k,v in decisions.items()}
            return ProjectState.model_validate(migrate_state(data))

    def snapshot(self,state:ProjectState)->int:
        project=state.model_dump(mode='json',exclude={'tasks','decisions'})
        with self._connect() as c:
            cur=c.execute('INSERT INTO snapshots(project_payload) VALUES(?)',(json.dumps(project,ensure_ascii=False,default=str),));return int(cur.lastrowid)


    def snapshot_full(self,state:ProjectState)->int:
        """Create a compressed, point-in-time full snapshot for milestone rollback."""
        raw=state.model_dump_json().encode("utf-8")
        payload=zlib.compress(raw,level=6)
        with self._lock,self._connect() as c:
            cur=c.execute("INSERT INTO full_snapshots(payload) VALUES(?)",(sqlite3.Binary(payload),))
            return int(cur.lastrowid)

    def restore_full_snapshot(self,seq:int)->ProjectState|None:
        with self._lock,self._connect() as c:
            row=c.execute("SELECT payload FROM full_snapshots WHERE seq=?",(int(seq),)).fetchone()
        if not row:return None
        data=json.loads(zlib.decompress(row[0]).decode("utf-8"))
        return ProjectState.model_validate(migrate_state(data))

    def integrity_check(self)->dict:
        with self._lock,self._connect() as c:
            result=str(c.execute("PRAGMA integrity_check").fetchone()[0])
            wal=str(c.execute("PRAGMA journal_mode").fetchone()[0])
        return {"ok":result.lower()=="ok","detail":result,"journal_mode":wal}

    def list_full_snapshots(self,limit:int=20)->list[dict]:
        with self._lock,self._connect() as c:
            rows=c.execute("SELECT seq,created_at,length(payload) FROM full_snapshots ORDER BY seq DESC LIMIT ?",(int(limit),)).fetchall()
        return [{"seq":int(seq),"created_at":created,"bytes":int(size)} for seq,created,size in rows]

    def latest_continuity(self)->dict|None:
        with self._lock,self._connect() as c:
            row=c.execute("SELECT payload FROM continuity_history ORDER BY seq DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def continuity_history(self,limit:int=20)->list[dict]:
        with self._lock,self._connect() as c:
            rows=c.execute("SELECT seq,created_at,payload FROM continuity_history ORDER BY seq DESC LIMIT ?",(int(limit),)).fetchall()
        out=[]
        for seq,created,payload in rows:
            item=json.loads(payload);item["seq"]=int(seq);item["stored_at"]=created;out.append(item)
        return out

    @staticmethod
    def prepare_for_resume(state:ProjectState)->ProjectState:
        if state.cancelled_at is not None or state.metadata.get("operator_cancelled"):
            state.paused = True
            state.autonomy_enabled = False
            return state
        ResumeCoordinator().prepare(state, source="sqlite_checkpoint_restart")
        return state
