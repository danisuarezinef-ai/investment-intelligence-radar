from __future__ import annotations

TEMPLATES = {
    "general": {"verification_percent": 50, "depth_percent": 60, "exploration_percent": 35},
    "research": {"verification_percent": 85, "depth_percent": 85, "exploration_percent": 60},
    "software": {"verification_percent": 75, "depth_percent": 70, "exploration_percent": 45},
}


def apply_template(state, name: str) -> None:
    cfg = TEMPLATES.get(name, TEMPLATES["general"])
    for key, value in cfg.items():
        setattr(state, key, value)
    state.metadata["project_template"] = name if name in TEMPLATES else "general"
    state.metadata.setdefault("enable_auto_batching", True)
    if name == "research":
        state.metadata["completion_confidence_threshold"] = 0.70
        if not state.completion_criteria: state.completion_criteria=["Search/discovery scope is exhausted or explicitly bounded.","Critical claims are verified or preserved as uncertainty.","Sources and provenance are auditable.","Final synthesis addresses the locked research question."]
    elif name == "software":
        state.metadata["completion_confidence_threshold"] = 0.60
        if not state.completion_criteria: state.completion_criteria=["Required behavior is implemented.","Automated tests for critical paths pass.","Known critical failures are resolved or documented.","Deliverable can be built or executed in its target environment."]
    else:
        state.metadata.setdefault("completion_confidence_threshold", 0.45)
        if not state.completion_criteria: state.completion_criteria=["Required outputs satisfy the locked goal.","No unresolved critical blocker remains."]
