from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, TaskStatus


class OperationsDashboardBuilder:
    """Produces compact chart-ready operational series from durable project state."""

    def build(self, state: ProjectState, *, bucket_minutes: int = 10, max_buckets: int = 36) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        seconds = max(60, int(bucket_minutes) * 60)
        buckets: dict[int, dict[str, float]] = defaultdict(lambda: {"completed": 0.0, "failures": 0.0, "recoveries": 0.0, "quality_sum": 0.0, "quality_n": 0.0})
        for task in state.leaf_tasks:
            when = task.completed_at or task.started_at
            if when is None:
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            idx = int(when.timestamp() // seconds)
            if task.status in {TaskStatus.COMPLETE, TaskStatus.PARTIAL_COMPLETE, TaskStatus.COMPLETE_WITH_UNCERTAINTY}:
                buckets[idx]["completed"] += 1
                if task.quality_score is not None:
                    buckets[idx]["quality_sum"] += float(task.quality_score)
                    buckets[idx]["quality_n"] += 1
            elif task.status == TaskStatus.FAILED:
                buckets[idx]["failures"] += 1
        for row in state.metadata.get("recovery_events", []) or []:
            try:
                ts = datetime.fromisoformat(str(row.get("ts")).replace("Z", "+00:00")).timestamp()
                buckets[int(ts // seconds)]["recoveries"] += 1
            except Exception:
                pass
        current_idx = int(now.timestamp() // seconds)
        start = current_idx - max_buckets + 1
        labels, completed, failures, recoveries, quality = [], [], [], [], []
        for idx in range(start, current_idx + 1):
            row = buckets[idx]
            dt = datetime.fromtimestamp(idx * seconds, tz=timezone.utc)
            labels.append(dt.isoformat())
            completed.append(int(row["completed"]))
            failures.append(int(row["failures"]))
            recoveries.append(int(row["recoveries"]))
            quality.append(round(row["quality_sum"] / row["quality_n"], 3) if row["quality_n"] else None)
        provider_rows = []
        for name, stats in (state.metadata.get("provider_stats", {}) or {}).items():
            runs = int(stats.get("runs", 0) or 0); fails = int(stats.get("failures", 0) or 0)
            provider_rows.append({
                "provider": name, "runs": runs, "failures": fails,
                "success_rate": round((runs - fails) / runs, 3) if runs else None,
                "average_seconds": stats.get("average_seconds"), "cost": stats.get("cost", 0.0),
            })
        provider_rows.sort(key=lambda x: (-x["runs"], x["provider"]))
        return {
            "bucket_minutes": bucket_minutes,
            "labels": labels,
            "series": {
                "completed": completed,
                "failures": failures,
                "recoveries": recoveries,
                "quality": quality,
            },
            "providers": provider_rows,
            "evidence_ledger": {
                "entries": len(state.metadata.get("evidence_ledger_v2", []) or []),
                "head": (state.metadata.get("evidence_ledger_v2_head") or {}).get("chain_hash"),
            },
        }
