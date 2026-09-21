from __future__ import annotations


def migrate_state(data: dict) -> dict:
    """Forward-compatible migration without forcing old checkpoints onto a new schema."""
    version = int(data.get("schema_version", 1) or 1)
    if version < 2:
        data.setdefault("verification_percent", 50)
        data.setdefault("exploration_percent", 35)
        data.setdefault("depth_percent", 60)
        data.setdefault("budget_limit", None)
        data.setdefault("priority_mode", "balanced")
        data.setdefault("absence_mode", False)
        for task in data.get("tasks", {}).values():
            task.setdefault("confidence", None)
            task.setdefault("quality_score", None)
            task.setdefault("cost_estimate", 0.0)
        data["schema_version"] = 2

    # v3+ fields remain backward-compatible through Pydantic defaults and metadata.
    meta = data.setdefault("metadata", {})
    for key, default in {
        "claims": {}, "sources": {}, "task_families": {}, "provider_task_stats": {},
        "completion_history": [], "project_summaries": {}, "marginal_yield_window": []
    }.items():
        meta.setdefault(key, default)
    return data
