from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable
import json
import re

from .models import ProjectState, Task, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-zA-ZÀ-ÿ0-9_\-]{3,}", str(text).lower())}


# ---------------------------------------------------------------------------
# Semantic memory and context compression
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MemoryItem:
    id: str
    kind: str
    text: str
    source_ref: str
    importance: float
    tags: list[str]
    created_at: str
    digest: str


class SemanticProjectMemory:
    KEY = "semantic_memory_v1"

    def add(self, state: ProjectState, *, kind: str, text: str, source_ref: str, importance: float = .5, tags: Iterable[str] = ()) -> MemoryItem:
        clean = " ".join(str(text).split())
        digest = _digest({"kind": kind, "text": clean, "source_ref": source_ref})
        mid = digest[:24]
        rows = state.metadata.setdefault(self.KEY, {})
        if mid in rows:
            return MemoryItem(**rows[mid])
        item = MemoryItem(mid, kind, clean, source_ref, round(max(0.0, min(1.0, float(importance))), 4), sorted(set(tags)), _now(), digest)
        rows[mid] = asdict(item)
        return item

    def ingest_project(self, state: ProjectState) -> int:
        before = len(state.metadata.setdefault(self.KEY, {}))
        for task_id, item in (state.metadata.get("knowledge", {}) or {}).items():
            self.add(
                state,
                kind="task_result",
                text=f"{item.get('title','')} {item.get('result','')}",
                source_ref=str(task_id),
                importance=float(item.get("quality") or .5),
                tags=["knowledge", str(item.get("provider") or "unknown")],
            )
        for decision in state.decisions.values():
            selected = decision.selected or decision.recommendation or "unresolved"
            self.add(
                state,
                kind="decision",
                text=f"{decision.title}. {decision.description}. Selected: {selected}",
                source_ref=decision.id,
                importance=.9 if decision.status.value != "open" else .7,
                tags=["decision", decision.status.value],
            )
        return len(state.metadata[self.KEY]) - before

    def search(self, state: ProjectState, query: str, limit: int = 8) -> list[dict[str, Any]]:
        q = _tokens(query)
        ranked = []
        for row in state.metadata.setdefault(self.KEY, {}).values():
            tokens = _tokens(row.get("text", "") + " " + " ".join(row.get("tags", [])))
            lexical = len(q & tokens) / max(1, len(q | tokens)) if q else 0.0
            score = lexical * .78 + float(row.get("importance", .5)) * .22
            if lexical or not q:
                ranked.append({**row, "score": round(score, 4)})
        return sorted(ranked, key=lambda x: (x["score"], x["created_at"]), reverse=True)[:max(1, limit)]


class ContextCompressor:
    """Compresses old context while preserving contractual and decision invariants."""

    def compress(self, state: ProjectState, max_words: int = 900) -> dict[str, Any]:
        critical_decisions = []
        for d in state.decisions.values():
            if d.status.value != "open":
                critical_decisions.append({"id": d.id, "title": d.title, "selected": d.selected, "recommendation": d.recommendation, "source": "project_decision"})
        # DecisionLedger contains durable governing decisions that may no longer
        # have a live Decision object. Preserve them during context compaction.
        for row in state.metadata.get("decision_ledger_v1", {}).values():
            critical_decisions.append({
                "id": row.get("id"),
                "title": row.get("topic"),
                "selected": row.get("selected"),
                "recommendation": row.get("recommendation"),
                "source": "decision_ledger",
            })
        unresolved = [
            {"id": t.id, "title": t.title, "status": t.status.value}
            for t in state.leaf_tasks
            if t.status not in {TaskStatus.COMPLETE, TaskStatus.SUPERSEDED}
        ][:80]
        recent_ids = list(state.metadata.get("result_order", []))[-30:]
        knowledge = state.metadata.get("knowledge", {}) or {}
        recent = []
        words = 0
        for tid in reversed(recent_ids):
            item = knowledge.get(tid)
            if not item:
                continue
            text = " ".join(str(item.get("result", "")).split())
            chunk_words = text.split()
            remaining = max_words - words
            if remaining <= 0:
                break
            snippet = " ".join(chunk_words[:remaining])
            words += len(snippet.split())
            recent.append({"task_id": tid, "title": item.get("title"), "summary": snippet, "digest": item.get("digest")})
        compressed = {
            "goal": state.goal,
            "goal_hash": state.metadata.get("goal_contract_hash"),
            "constraints": list(state.goal_constraints),
            "forbidden_actions": list(state.metadata.get("forbidden_actions", [])),
            "deliverables": list(state.goal_deliverables),
            "completion_criteria": list(state.completion_criteria),
            "decisions": critical_decisions[-100:],
            "binding_decisions": list((state.metadata.get("binding_decisions_v2", {}) or {}).values()),
            "unresolved": unresolved,
            "recent_knowledge": list(reversed(recent)),
            "evidence_digest": _digest(state.metadata.get("evidence_ledger_v2", [])),
            "compressed_at": _now(),
        }
        compressed["digest"] = _digest(compressed)
        state.metadata["compressed_context_v1"] = compressed
        return compressed


# ---------------------------------------------------------------------------
# Decision ledger
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DecisionLedgerEntry:
    id: str
    topic: str
    options: list[str]
    selected: str
    recommendation: str | None
    rationale: str
    evidence_ids: list[str]
    reversible: bool
    goal_hash: str | None
    created_at: str
    outcome: str | None = None


class DecisionLedger:
    KEY = "decision_ledger_v1"

    def record(
        self,
        state: ProjectState,
        *,
        topic: str,
        options: Iterable[str],
        selected: str,
        rationale: str,
        recommendation: str | None = None,
        evidence_ids: Iterable[str] = (),
        reversible: bool = True,
    ) -> DecisionLedgerEntry:
        payload = {
            "topic": topic.strip(),
            "options": list(options),
            "selected": selected,
            "recommendation": recommendation,
            "rationale": rationale,
            "evidence_ids": sorted(set(evidence_ids)),
            "reversible": bool(reversible),
            "goal_hash": state.metadata.get("goal_contract_hash"),
        }
        entry = DecisionLedgerEntry(_digest(payload)[:24], created_at=_now(), **payload)
        state.metadata.setdefault(self.KEY, {})[entry.id] = asdict(entry)
        return entry

    def update_outcome(self, state: ProjectState, entry_id: str, outcome: str) -> bool:
        row = state.metadata.setdefault(self.KEY, {}).get(entry_id)
        if not row:
            return False
        row["outcome"] = outcome; row["outcome_at"] = _now(); return True

    def prior_for_topic(self, state: ProjectState, topic: str) -> list[DecisionLedgerEntry]:
        topic_tokens = _tokens(topic)
        rows = []
        for row in state.metadata.setdefault(self.KEY, {}).values():
            overlap = len(topic_tokens & _tokens(row.get("topic", ""))) / max(1, len(topic_tokens | _tokens(row.get("topic", ""))))
            if overlap >= .5:
                rows.append((overlap, DecisionLedgerEntry(**{k: v for k, v in row.items() if k in DecisionLedgerEntry.__dataclass_fields__})))
        return [x[1] for x in sorted(rows, key=lambda x: x[0], reverse=True)]

    def should_reopen(self, state: ProjectState, prior_id: str, new_evidence_ids: Iterable[str] = ()) -> dict[str, Any]:
        row = state.metadata.setdefault(self.KEY, {}).get(prior_id)
        if not row:
            return {"reopen": True, "reason": "prior_decision_missing"}
        if row.get("goal_hash") != state.metadata.get("goal_contract_hash"):
            return {"reopen": True, "reason": "goal_contract_changed"}
        prior_evidence = set(row.get("evidence_ids", [])); new = set(new_evidence_ids)
        if new - prior_evidence:
            return {"reopen": True, "reason": "material_new_evidence"}
        return {"reopen": False, "reason": "decision_still_governed_by_same_goal_and_evidence"}


# ---------------------------------------------------------------------------
# Artifact manager and versioning
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ArtifactVersion:
    version: int
    digest: str
    source_ref: str
    task_id: str | None
    status: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ArtifactManager:
    KEY = "artifact_registry_v1"

    def register(
        self,
        state: ProjectState,
        *,
        artifact_id: str,
        source_ref: str,
        content_or_hash: str,
        task_id: str | None = None,
        status: str = "produced",
        dependencies: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactVersion:
        registry = state.metadata.setdefault(self.KEY, {})
        row = registry.setdefault(artifact_id, {"artifact_id": artifact_id, "versions": [], "dependencies": sorted(set(dependencies))})
        digest = content_or_hash if re.fullmatch(r"[0-9a-fA-F]{64}", content_or_hash) else sha256(content_or_hash.encode()).hexdigest()
        existing = next((v for v in row["versions"] if v.get("digest") == digest), None)
        if existing:
            return ArtifactVersion(**existing)
        version = ArtifactVersion(len(row["versions"]) + 1, digest, source_ref, task_id, status, _now(), dict(metadata or {}))
        row["versions"].append(asdict(version)); row["current_version"] = version.version; row["status"] = status
        return version

    def current(self, state: ProjectState, artifact_id: str) -> ArtifactVersion | None:
        row = state.metadata.setdefault(self.KEY, {}).get(artifact_id)
        if not row or not row.get("versions"):
            return None
        version = int(row.get("current_version", len(row["versions"])))
        return ArtifactVersion(**row["versions"][version - 1])

    def rollback_version(self, state: ProjectState, artifact_id: str, version: int) -> ArtifactVersion | None:
        row = state.metadata.setdefault(self.KEY, {}).get(artifact_id)
        if not row or version < 1 or version > len(row.get("versions", [])):
            return None
        row["current_version"] = int(version); row["status"] = row["versions"][version - 1].get("status", "produced")
        row.setdefault("history", []).append({"event": "rollback", "version": int(version), "ts": _now()})
        return ArtifactVersion(**row["versions"][version - 1])

    def verify(self, state: ProjectState, artifact_id: str, evidence_ids: Iterable[str]) -> bool:
        row = state.metadata.setdefault(self.KEY, {}).get(artifact_id)
        if not row:
            return False
        row["verified"] = True; row["verification_evidence"] = sorted(set(evidence_ids)); row["verified_at"] = _now(); return True


# ---------------------------------------------------------------------------
# Skills, outcome learning and evolution registry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SkillVersion:
    version: int
    procedure: list[str]
    tests: list[str]
    created_at: str
    digest: str


class SkillLibrary:
    KEY = "skills_library_v1"
    STAGES = ("experimental", "tested", "verified", "preferred")

    def add_version(self, state: ProjectState, name: str, procedure: Iterable[str], tests: Iterable[str] = ()) -> SkillVersion:
        rows = state.metadata.setdefault(self.KEY, {})
        row = rows.setdefault(name, {"name": name, "stage": "experimental", "versions": [], "successes": 0, "failures": 0})
        payload = {"procedure": list(procedure), "tests": list(tests)}
        digest = _digest(payload)
        existing = next((v for v in row["versions"] if v.get("digest") == digest), None)
        if existing:
            return SkillVersion(**existing)
        version = SkillVersion(len(row["versions"]) + 1, payload["procedure"], payload["tests"], _now(), digest)
        row["versions"].append(asdict(version)); row["current_version"] = version.version
        return version

    def record_outcome(self, state: ProjectState, name: str, success: bool, independently_verified: bool = False) -> str | None:
        row = state.metadata.setdefault(self.KEY, {}).get(name)
        if not row:
            return None
        row["successes" if success else "failures"] += 1
        s, f = int(row["successes"]), int(row["failures"])
        stage = row.get("stage", "experimental")
        if stage == "experimental" and s >= 2 and f == 0:
            stage = "tested"
        if stage == "tested" and independently_verified and s >= 4 and s >= max(1, f) * 2:
            stage = "verified"
        if stage == "verified" and s >= 8 and s >= max(1, f) * 4:
            stage = "preferred"
        if f > s and stage in {"verified", "preferred"}:
            stage = "tested"
        row["stage"] = stage; row["updated_at"] = _now()
        return stage

    def preferred(self, state: ProjectState) -> list[str]:
        return sorted(name for name, row in state.metadata.setdefault(self.KEY, {}).items() if row.get("stage") == "preferred")


class OutcomeLearningEngine:
    KEY = "outcome_learning_v1"

    def record(self, state: ProjectState, *, task_type: str, strategy: str, success: bool, quality: float, cost: float, seconds: float) -> dict[str, Any]:
        root = state.metadata.setdefault(self.KEY, {})
        key = f"{task_type}|{strategy}"
        row = root.setdefault(key, {"task_type": task_type, "strategy": strategy, "runs": 0, "successes": 0, "quality_sum": 0.0, "cost_sum": 0.0, "seconds_sum": 0.0})
        row["runs"] += 1; row["successes"] += int(success); row["quality_sum"] += max(0.0, min(1.0, float(quality))); row["cost_sum"] += max(0.0, float(cost)); row["seconds_sum"] += max(0.0, float(seconds))
        row["success_rate"] = round(row["successes"] / row["runs"], 4)
        row["avg_quality"] = round(row["quality_sum"] / row["runs"], 4)
        row["avg_cost"] = round(row["cost_sum"] / row["runs"], 6)
        row["avg_seconds"] = round(row["seconds_sum"] / row["runs"], 4)
        row["utility"] = round(row["success_rate"] * .45 + row["avg_quality"] * .4 + (1 / (1 + row["avg_cost"])) * .08 + (1 / (1 + row["avg_seconds"] / 60)) * .07, 4)
        return row

    def rank(self, state: ProjectState, task_type: str) -> list[dict[str, Any]]:
        rows = [dict(row) for row in state.metadata.setdefault(self.KEY, {}).values() if row.get("task_type") == task_type]
        return sorted(rows, key=lambda x: (x.get("utility", 0), x.get("runs", 0)), reverse=True)


@dataclass(slots=True)
class EvolutionEntry:
    id: str
    parent_id: str | None
    generation: int
    hypothesis: str
    change: str
    benchmark_before: float
    benchmark_after: float
    tests_passed: bool
    security_regressions: int
    status: str
    reason: str
    created_at: str


class EvolutionRegistry:
    KEY = "evolution_registry_v1"

    def register(
        self,
        state: ProjectState,
        *,
        hypothesis: str,
        change: str,
        benchmark_before: float,
        benchmark_after: float,
        tests_passed: bool,
        security_regressions: int = 0,
        parent_id: str | None = None,
    ) -> EvolutionEntry:
        rows = state.metadata.setdefault(self.KEY, {})
        parent = rows.get(parent_id) if parent_id else None
        generation = int(parent.get("generation", 0)) + 1 if parent else 0
        safe_gain = float(benchmark_after) > float(benchmark_before) and tests_passed and security_regressions == 0
        status = "candidate" if safe_gain else "rejected"
        reason = "safe measurable improvement" if safe_gain else "no safe out-of-sample improvement"
        eid = _digest({"parent": parent_id, "hypothesis": hypothesis, "change": change, "generation": generation})[:24]
        entry = EvolutionEntry(eid, parent_id, generation, hypothesis, change, float(benchmark_before), float(benchmark_after), bool(tests_passed), int(security_regressions), status, reason, _now())
        rows[eid] = asdict(entry)
        return entry

    def promote(self, state: ProjectState, entry_id: str, *, independent_gate_passed: bool) -> bool:
        row = state.metadata.setdefault(self.KEY, {}).get(entry_id)
        if not row or row.get("status") != "candidate" or not independent_gate_passed:
            return False
        for other in state.metadata[self.KEY].values():
            if other.get("status") == "active":
                other["status"] = "hall_of_fame"
        row["status"] = "active"; row["promoted_at"] = _now(); return True

    def graveyard(self, state: ProjectState) -> list[dict[str, Any]]:
        return [row for row in state.metadata.setdefault(self.KEY, {}).values() if row.get("status") == "rejected"]


class LongHorizonMemoryAuditor:
    """Checks that compression does not discard governing decisions/invariants."""

    def audit(self, state: ProjectState) -> dict[str, Any]:
        compressed = ContextCompressor().compress(state)
        ledger = state.metadata.get(DecisionLedger.KEY, {})
        selected = {row.get("selected") for row in ledger.values() if row.get("selected")}
        compressed_selected = {row.get("selected") for row in compressed.get("decisions", []) if row.get("selected")}
        missing = sorted(selected - compressed_selected)
        invariants = {
            "goal_present": compressed.get("goal") == state.goal,
            "constraints_preserved": set(state.goal_constraints).issubset(set(compressed.get("constraints", []))),
            "forbidden_preserved": set(state.metadata.get("forbidden_actions", [])).issubset(set(compressed.get("forbidden_actions", []))),
            "decisions_preserved": not missing,
        }
        return {"pass": all(invariants.values()), "invariants": invariants, "missing_decision_values": missing, "compressed_digest": compressed.get("digest")}
