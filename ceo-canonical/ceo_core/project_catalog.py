from __future__ import annotations

import json
import shutil
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4
from typing import Any

from .models import ProjectState
from .progress_tracker import StableProgressTracker
from .sqlite_store import SqliteCheckpointStore
from .portfolio_supervisor import PortfolioSupervisor


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectCatalog:
    """Persistent catalog for multiple independent CEO projects.

    Each project gets its own SQLite checkpoint store.  The catalog contains only
    project-level metadata and the active project id, so a damaged project database
    cannot corrupt the others.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "catalog.json"
        self._lock = RLock()
        self.progress_tracker = StableProgressTracker()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"active_project_id": None, "projects": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            data.setdefault("active_project_id", None)
            data.setdefault("projects", {})
            return data
        except (OSError, json.JSONDecodeError):
            return {"active_project_id": None, "projects": {}}

    def _save(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def store_path(self, project_id: str) -> Path:
        safe = "".join(c for c in project_id if c.isalnum() or c in "-_")
        if not safe or safe != project_id:
            raise ValueError("Invalid project id")
        folder = self.root / safe
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "ceo.db"

    def store(self, project_id: str) -> SqliteCheckpointStore:
        return SqliteCheckpointStore(self.store_path(project_id))

    def register(self, state: ProjectState, *, make_active: bool = True) -> dict[str, Any]:
        with self._lock:
            data = self._load()
            projects = data["projects"]
            previous = projects.get(state.id, {})
            progress = self.progress_tracker.snapshot(state, persist=True)
            row = {
                "id": state.id,
                "name": state.project_name or state.goal[:80] or "Proyecto",
                "goal": state.goal,
                "progress": progress["display_progress"],
                "batch_progress": progress["batch_progress"],
                "productive_completed": progress["productive_completed"],
                "productive_total_known": progress["productive_total_known"],
                "last_productive_progress_at": progress["last_productive_progress_at"],
                "paused": state.paused,
                "archived": state.archived,
                "completed_at": state.completed_at.isoformat() if state.completed_at else None,
                "cancelled_at": state.cancelled_at.isoformat() if state.cancelled_at else None,
                "cancelled_reason": state.cancelled_reason,
                "created_at": previous.get("created_at") or state.created_at.isoformat(),
                "updated_at": _now(),
                "store": str(self.store_path(state.id)),
                "task_count": len(state.leaf_tasks),
                "completed_tasks": len(state.completed_leaf_tasks),
                "needs_attention": len([t for t in state.leaf_tasks if t.status.value in {"failed", "needs_review", "blocked"}]),
                "next_action": (state.metadata.get("continuity_snapshot") or {}).get("next", [{}])[0].get("title") if (state.metadata.get("continuity_snapshot") or {}).get("next") else None,
            }
            projects[state.id] = row
            if make_active:
                data["active_project_id"] = state.id
            self._save(data)
            return dict(row)

    def touch(self, state: ProjectState) -> None:
        self.register(state, make_active=False)

    def active_project_id(self) -> str | None:
        with self._lock:
            return self._load().get("active_project_id")

    def set_active(self, project_id: str | None) -> None:
        with self._lock:
            data = self._load()
            if project_id is not None and project_id not in data.get("projects", {}):
                raise KeyError(project_id)
            data["active_project_id"] = project_id
            self._save(data)

    def list(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            data = self._load()
            active = data.get("active_project_id")
            rows = []
            for row in data.get("projects", {}).values():
                if row.get("archived") and not include_archived:
                    continue
                item = dict(row)
                item["active"] = item.get("id") == active
                rows.append(item)
            rows.sort(key=lambda x: str(x.get("updated_at", "")), reverse=True)
            return rows


    def portfolio_list(self, *, include_archived: bool = False, total_slots: int = 8) -> list[dict[str, Any]]:
        """Return catalog rows enriched with an advisory cross-project capacity plan.

        The planner never unpauses or starts projects. It only records ranking/slot
        advice so the operator and a future multi-project runtime can make informed
        choices without weakening existing project-level gates.
        """
        rows = self.list(include_archived=include_archived)
        states: list[ProjectState] = []
        stores: dict[str, SqliteCheckpointStore] = {}
        for row in rows:
            pid = str(row.get("id") or "")
            if not pid:
                continue
            try:
                store = self.store(pid)
                state = store.load()
            except Exception:
                continue
            if state is not None:
                states.append(state)
                stores[state.id] = store
        plan = PortfolioSupervisor().plan(states, total_slots=max(0, int(total_slots)))
        by_id = {str(x["project_id"]): x for x in plan.get("projects", [])}
        for state in states:
            try:
                stores[state.id].save(state)
            except Exception:
                pass
        for row in rows:
            advisory = by_id.get(str(row.get("id") or ""))
            if advisory:
                row["portfolio"] = advisory
        rows.sort(key=lambda r: (int((r.get("portfolio") or {}).get("rank", 10**9)), str(r.get("updated_at", ""))))
        return rows

    def duplicate(self, project_id: str, *, name: str | None = None, make_active: bool = False) -> ProjectState:
        source_store = self.store(project_id)
        source = source_store.load()
        if source is None:
            raise KeyError(project_id)
        clone = source.model_copy(deep=True)
        clone.id = uuid4().hex
        clone.project_name = (name or f"{source.project_name or source.goal[:60]} (copia)").strip()
        clone.archived = False
        clone.paused = True
        clone.completed_at = None if source.completed_at is None else source.completed_at
        clone.metadata = dict(clone.metadata)
        clone.metadata["duplicated_from"] = project_id
        clone.metadata["duplicated_at"] = _now()
        clone.metadata.pop("continuity_snapshot", None)
        target = self.store(clone.id)
        target.save(clone)
        self.register(clone, make_active=make_active)
        return clone

    def set_paused(self, project_id: str, paused: bool) -> ProjectState:
        store = self.store(project_id)
        state = store.load()
        if state is None:
            raise KeyError(project_id)
        state.paused = bool(paused)
        store.save(state)
        self.register(state, make_active=False)
        return state


    def reconcile_storage(self) -> dict[str, Any]:
        """Repair catalog/store drift without deleting user data.

        The catalog path is authoritative. Historical ``store`` strings are rewritten
        to the canonical per-project location and orphan project folders containing a
        valid ``ceo.db`` are re-indexed. No project is deleted or archived here.
        """
        with self._lock:
            data = self._load()
            repaired: list[str] = []
            discovered: list[str] = []
            invalid: list[str] = []
            for project_id, row in list(data.get("projects", {}).items()):
                try:
                    canonical = str(self.store_path(project_id))
                except ValueError:
                    invalid.append(project_id)
                    continue
                if row.get("store") != canonical:
                    row["store"] = canonical
                    row["updated_at"] = _now()
                    repaired.append(project_id)

            for child in self.root.iterdir():
                if not child.is_dir():
                    continue
                db = child / "ceo.db"
                if not db.exists() or child.name in data.get("projects", {}):
                    continue
                try:
                    state = SqliteCheckpointStore(db).load()
                except Exception:
                    continue
                if state is None or state.id != child.name:
                    continue
                progress = self.progress_tracker.snapshot(state, persist=False)
                data["projects"][state.id] = {
                    "id": state.id,
                    "name": state.project_name or state.goal[:80] or "Proyecto",
                    "goal": state.goal,
                    "progress": progress["display_progress"],
                    "batch_progress": progress["batch_progress"],
                    "productive_completed": progress["productive_completed"],
                    "productive_total_known": progress["productive_total_known"],
                    "last_productive_progress_at": progress["last_productive_progress_at"],
                    "paused": state.paused,
                    "archived": state.archived,
                    "completed_at": state.completed_at.isoformat() if state.completed_at else None,
                    "created_at": state.created_at.isoformat(),
                    "updated_at": _now(),
                    "store": str(db),
                    "task_count": len(state.leaf_tasks),
                    "completed_tasks": len(state.completed_leaf_tasks),
                    "needs_attention": len([t for t in state.leaf_tasks if t.status.value in {"failed", "needs_review", "blocked"}]),
                    "next_action": None,
                }
                discovered.append(state.id)
            if repaired or discovered:
                self._save(data)
            return {"repaired_store_paths": repaired, "discovered_projects": discovered, "invalid_project_ids": invalid}

    def migrate_legacy_store(self, legacy_path: str | Path) -> dict[str, Any]:
        """Import a historical single-project DB exactly once into canonical storage."""
        legacy = Path(legacy_path)
        marker = self.root / ".legacy_store_migration.json"
        if marker.exists() or not legacy.exists():
            return {"migrated": False, "reason": "already_migrated_or_absent"}
        try:
            state = SqliteCheckpointStore(legacy).load()
        except Exception as exc:
            marker.write_text(json.dumps({"migrated": False, "error": str(exc), "ts": _now()}, indent=2), encoding="utf-8")
            return {"migrated": False, "reason": "legacy_load_failed", "error": str(exc)}
        if state is None:
            marker.write_text(json.dumps({"migrated": False, "reason": "empty", "ts": _now()}, indent=2), encoding="utf-8")
            return {"migrated": False, "reason": "empty"}
        target = self.store(state.id)
        existing = target.load()
        if existing is None:
            target.save(state)
            self.register(state, make_active=self.active_project_id() is None)
            migrated = True
        else:
            migrated = False
        marker.write_text(json.dumps({"migrated": migrated, "project_id": state.id, "ts": _now()}, indent=2), encoding="utf-8")
        return {"migrated": migrated, "project_id": state.id}

    def migrate_projects(self) -> dict[str, Any]:
        """Apply non-destructive compatibility migration to all catalogued projects."""
        report = {"scanned": 0, "updated": [], "errors": []}
        for row in self.list(include_archived=True):
            project_id = str(row["id"])
            report["scanned"] += 1
            try:
                store = self.store(project_id)
                state = store.load()
                if state is None:
                    report["errors"].append({"project_id": project_id, "error": "missing_state"})
                    continue
                changed = False
                md = state.metadata.setdefault("project_migration_v1", {})
                if not md.get("applied"):
                    md.update({"applied": True, "applied_at": _now(), "source_schema": int(state.schema_version)})
                    changed = True
                # Preserve user text but identify obvious historical placeholders for assisted cleanup.
                name = (state.project_name or "").strip().lower()
                if name in {"x", "continua", "continúa", "continua con el trabajo anterior", "continue"}:
                    state.metadata["cleanup_candidate_reason"] = "historical_placeholder_name"
                    changed = True
                if changed:
                    store.save(state)
                    self.register(state, make_active=False)
                    report["updated"].append(project_id)
            except Exception as exc:
                report["errors"].append({"project_id": project_id, "error": f"{type(exc).__name__}: {exc}"})
        return report

    def cleanup_candidates(self) -> list[dict[str, Any]]:
        """Return cleanup suggestions only; never mutates or deletes projects."""
        rows = self.list(include_archived=True)
        goals: dict[str, list[str]] = {}
        for row in rows:
            goal = " ".join(str(row.get("goal") or "").lower().split())
            if goal:
                goals.setdefault(sha256(goal.encode()).hexdigest()[:16], []).append(str(row["id"]))
        candidates: list[dict[str, Any]] = []
        placeholders = {"x", "continua", "continúa", "continua con el trabajo anterior", "continue"}
        for row in rows:
            reasons: list[str] = []
            name = str(row.get("name") or "").strip().lower()
            goal = " ".join(str(row.get("goal") or "").lower().split())
            if name in placeholders or goal in placeholders:
                reasons.append("placeholder_historical")
            if not goal or (int(row.get("task_count") or 0) == 0 and not row.get("completed_at")):
                reasons.append("empty_or_no_work")
            if goal:
                group = goals.get(sha256(goal.encode()).hexdigest()[:16], [])
                if len(group) > 1:
                    reasons.append("duplicate_goal")
            if row.get("archived"):
                reasons.append("already_archived")
            if reasons:
                candidates.append({
                    "project_id": row["id"],
                    "name": row.get("name"),
                    "active": bool(row.get("active")),
                    "reasons": reasons,
                    "recommended_action": "review_then_archive_or_delete",
                    "automatic_action": False,
                })
        return candidates

    def delete(self, project_id: str, *, confirmation: str, allow_active: bool = False) -> dict[str, Any]:
        """Permanently delete a project only with exact explicit confirmation."""
        if confirmation != project_id:
            raise PermissionError("Exact project id confirmation required")
        with self._lock:
            data = self._load()
            if project_id not in data.get("projects", {}):
                raise KeyError(project_id)
            if data.get("active_project_id") == project_id and not allow_active:
                raise RuntimeError("Active project must be stopped before deletion")
            folder = self.root / project_id
            canonical = self.store_path(project_id).parent
            if canonical != folder:
                raise RuntimeError("Refusing non-canonical delete target")
            data["projects"].pop(project_id, None)
            if data.get("active_project_id") == project_id:
                data["active_project_id"] = None
            self._save(data)
            if folder.exists():
                shutil.rmtree(folder)
            return {"deleted": True, "project_id": project_id}

    def archive(self, project_id: str, archived: bool = True) -> None:
        # Persist the lifecycle flag in both the project DB and the lightweight catalog.
        try:
            store = self.store(project_id)
            state = store.load()
        except Exception:
            state = None
        if state is not None:
            state.archived = bool(archived)
            if archived:
                state.paused = True
            store.save(state)
        with self._lock:
            data = self._load()
            row = data.get("projects", {}).get(project_id)
            if not row:
                raise KeyError(project_id)
            row["archived"] = bool(archived)
            if archived:
                row["paused"] = True
            row["updated_at"] = _now()
            if archived and data.get("active_project_id") == project_id:
                data["active_project_id"] = None
            self._save(data)

