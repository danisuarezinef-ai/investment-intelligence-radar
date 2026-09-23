from __future__ import annotations

import hashlib
import json
import os
import pathlib


REPO = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "ceo-browser" / "w9_local_finite_provider_template.py"


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

    text = replace_once(
        text,
        "        from ceo_core.goal_lock_local_provider_v1 import GoalLockLocalProviderV1\n",
        "        from ceo_core.goal_lock_local_provider_v1 import GoalLockLocalProviderV1\n"
        "        from ceo_core.local_finite_file_provider_v1 import (\n"
        "            LocalFiniteFileProviderV1,\n"
        "            configure_local_finite_file_state,\n"
        "            parse_local_finite_file_goal,\n"
        "        )\n",
        "W9 import",
    )

    text = replace_once(
        text,
        "        self.GoalLockLocalProviderV1 = GoalLockLocalProviderV1\n",
        "        self.GoalLockLocalProviderV1 = GoalLockLocalProviderV1\n"
        "        self.LocalFiniteFileProviderV1 = LocalFiniteFileProviderV1\n"
        "        self.configure_local_finite_file_state = configure_local_finite_file_state\n"
        "        self.parse_local_finite_file_goal = parse_local_finite_file_goal\n",
        "W9 class bindings",
    )

    text = replace_once(
        text,
        "        local_goal_lock = self.GoalLockLocalProviderV1()\n"
        "        providers = [local_goal_lock]\n",
        "        local_goal_lock = self.GoalLockLocalProviderV1()\n"
        "        local_finite_file = self.LocalFiniteFileProviderV1()\n"
        "        providers = [local_goal_lock, local_finite_file]\n",
        "W9 router",
    )

    start = text.index("    async def start_project(self, body: dict[str, Any]):")
    end = text.find("\n    async def ", start + 20)
    if end < 0:
        raise RuntimeError("W9 start_project end not found")
    block = text[start:end]

    block = replace_once(
        block,
        '        goal_text = str(body.get("goal") or "").strip()\n'
        '        if len(goal_text) < 3:\n'
        '            raise ValueError("El objetivo debe tener al menos 3 caracteres")\n',
        '        goal_text = str(body.get("goal") or "").strip()\n'
        '        if len(goal_text) < 3:\n'
        '            raise ValueError("El objetivo debe tener al menos 3 caracteres")\n'
        '        local_finite_spec = self.parse_local_finite_file_goal(goal_text)\n',
        "W9 goal parse",
    )

    planner_anchor = "        planner = self.BaselineTaskPlanner(self.TaskDecomposer())\n"
    block = replace_once(
        block,
        planner_anchor,
        '        if local_finite_spec:\n'
        '            goal.deliverables = [str(local_finite_spec["path"])]\n'
        '            goal.success_definition = (\n'
        '                f"{local_finite_spec[\'path\']} exists in the CEO workspace and "\n'
        '                "contains exactly the requested content."\n'
        '            )\n'
        '            goal.completion_criteria = [\n'
        '                "Requested local file exists inside the managed workspace.",\n'
        '                "Requested exact content matches after UTF-8 readback.",\n'
        '                "Independent local verification passes.",\n'
        '            ]\n'
        + planner_anchor,
        "W9 goal specialization",
    )

    workspace_anchor = "        self._ensure_project_workspace(state)\n"
    block = replace_once(
        block,
        workspace_anchor,
        '        workspace_root = self._ensure_project_workspace(state)\n'
        '        if local_finite_spec:\n'
        '            self.configure_local_finite_file_state(state, local_finite_spec, workspace_root)\n'
        '            state.metadata["local_execution_enabled_v1"] = True\n',
        "W9 workspace configure",
    )

    provider_wait_anchor = "        if not self.execution_enabled:\n"
    if provider_wait_anchor in block:
        block = block.replace(
            provider_wait_anchor,
            "        if not self.execution_enabled and not local_finite_spec:\n",
            1,
        )

    store_anchor = "        store = self.projects.store(state.id)\n"
    block = replace_once(
        block,
        store_anchor,
        '        if local_finite_spec:\n'
        '            state.metadata.pop("provider_wait_v1", None)\n'
        '            state.metadata.pop("execution_disabled_reason", None)\n'
        '            state.metadata["provider_mode"] = "local-finite-file"\n'
        + store_anchor,
        "W9 local mode marker",
    )

    text = text[:start] + block + text[end:]
    path.write_text(text, encoding="utf-8")


def apply(root: pathlib.Path) -> dict:
    root = root.resolve()
    if not TEMPLATE.is_file():
        raise RuntimeError(f"missing W9 template: {TEMPLATE}")

    module = root / "ceo_core" / "local_finite_file_provider_v1.py"
    module.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")

    work_mode = root / "scripts" / "ceo_stdlib_work_mode.py"
    patch_work_mode(work_mode)

    contract_path = root / "CEO_UPDATE_PACKAGE.json"
    updated_paths: list[str] = []
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        hashes = dict(contract.get("file_hashes") or {})
        for relative in (
            "ceo_core/local_finite_file_provider_v1.py",
            "scripts/ceo_stdlib_work_mode.py",
        ):
            hashes[relative] = sha256_file(root / relative)
            updated_paths.append(relative)
        contract["file_hashes"] = hashes

        required = contract.get("required_files")
        if isinstance(required, list):
            for relative in updated_paths:
                if relative not in required:
                    required.append(relative)

        contract_path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return {
        "ok": True,
        "module_sha256": sha256_file(module),
        "work_mode_sha256": sha256_file(work_mode),
        "contract_paths_updated": updated_paths,
    }


def main() -> int:
    root_text = str(os.environ.get("CEO_W9_ROOT") or "").strip()
    if not root_text:
        raise RuntimeError("CEO_W9_ROOT is required")

    out = apply(pathlib.Path(root_text))
    print("W9_LOCAL_FINITE_PATCH_APPLIED")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
