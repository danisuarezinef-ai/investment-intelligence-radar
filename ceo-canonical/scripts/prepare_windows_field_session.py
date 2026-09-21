from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState
from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_field import SelfHostingFieldOpsCore

PROJECT_ID = "windows-self-hosting-field"


def main() -> int:
    root = user_data_root()
    catalog = ProjectCatalog(root / "projects")
    store = catalog.store(PROJECT_ID)
    state = store.load()
    created = False
    if state is None:
        state = ProjectState(
            id=PROJECT_ID,
            project_name="CEO Windows Field Validation",
            goal="Validate CEO de IAs Self-Hosting Alpha safely on a physical Windows machine",
            goal_definition="Execute field missions 76-85 with signed evidence and no automatic promotion.",
            goal_success_definition="Physical Windows/Chrome/ChatGPT gates are verified with signed evidence while stable CEO remains unchanged.",
            completion_criteria=[
                "Windows read-only mission verified",
                "Chrome navigation/session/download verified",
                "Multi-app mission verified",
                "ChatGPT worker and multi-turn verified",
                "Self-improvement field mission verified",
                "Alpha certification verified",
                "Supervised dogfooding started",
            ],
            goal_constraints=[
                "Never auto-promote a candidate",
                "Never overwrite the running stable version",
                "Treat mocks/synthetic runs as non-field evidence",
                "Require human confirmation for authenticated-session and recovery attestations",
            ],
            autonomy_enabled=True,
            power_percent=20,
            verification_percent=90,
        )
        created = True
    core = SelfHostingFieldOpsCore()
    core.initialize(state)
    state.metadata.setdefault("windows_field_session", {})["prepared"] = True
    store.save(state)
    catalog.register(state, make_active=True)
    out = {
        "ok": True,
        "created": created,
        "project_id": state.id,
        "project_name": state.project_name,
        "data_root": str(root),
        "active_project_id": catalog.active_project_id(),
        "field_certification": core.snapshot(state)["certification"],
    }
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
