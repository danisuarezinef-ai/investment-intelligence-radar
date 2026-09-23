from __future__ import annotations

import hashlib
import json
import os
import pathlib


REPO = pathlib.Path(__file__).resolve().parents[1]
ROOT = pathlib.Path(os.environ["CEO_W13_ROOT"]).resolve()
CANONICAL_DRIVER = REPO / "ceo-browser" / "windows_chatgpt_cdp_driver.ps1"
CANONICAL_PROFILE = REPO / "ceo-browser" / "open_chatgpt_profile.ps1"
CANONICAL_RECIPE = REPO / "ceo-browser" / "recipes" / "chatgpt_web.json"
OLD_DRIVER = REPO / "ceo-updates" / "dev313-inspect-routing" / "browser_ai" / "windows_chatgpt_cdp_driver.ps1"
OLD_RECIPE = REPO / "ceo-updates" / "dev313-inspect-routing" / "browser_ai" / "recipes" / "chatgpt_web.json"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def method_block(text: str, signature: str) -> str:
    start = text.index(signature)
    end = text.find("\n    async def ", start + len(signature))
    if end < 0:
        end = text.find("\n    def ", start + len(signature))
    if end < 0:
        end = len(text)
    return text[start:end]


def raw_case() -> None:
    targets = {
        "driver": ROOT / "ceo_core" / "browser_ai" / "windows_chatgpt_cdp_driver.ps1",
        "profile": ROOT / "ceo_core" / "browser_ai" / "open_chatgpt_profile.ps1",
        "recipe": ROOT / "ceo_core" / "browser_ai" / "recipes" / "chatgpt_web.json",
        "provider": ROOT / "ceo_core" / "providers" / "chatgpt_web.py",
    }
    work = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    row = {
        "missing": [name for name, path in targets.items() if not path.is_file()],
        "has_browser_transport_hook": "ChatGPTWebTransport" in work,
        "has_browser_primary_surface": "primary_ai_surface" in work,
        "canonical_driver_sha256": sha(CANONICAL_DRIVER),
        "old_driver_sha256": sha(OLD_DRIVER),
        "canonical_recipe_sha256": sha(CANONICAL_RECIPE),
        "old_recipe_sha256": sha(OLD_RECIPE),
    }
    print("W13_RAW_BROWSER_GAP", json.dumps(row, sort_keys=True))
    assert set(row["missing"]) == {"driver", "profile", "recipe", "provider"}, row
    assert row["has_browser_transport_hook"] is False, row
    assert row["has_browser_primary_surface"] is False, row
    assert row["canonical_driver_sha256"] != row["old_driver_sha256"], row
    assert row["canonical_recipe_sha256"] != row["old_recipe_sha256"], row
    print("W13_RAW_BROWSER_WORKER_GAP_REPRODUCED")


def patched_case() -> None:
    rels = {
        "driver": "ceo_core/browser_ai/windows_chatgpt_cdp_driver.ps1",
        "profile": "ceo_core/browser_ai/open_chatgpt_profile.ps1",
        "recipe": "ceo_core/browser_ai/recipes/chatgpt_web.json",
        "provider": "ceo_core/providers/chatgpt_web.py",
        "routing": "ceo_core/routing.py",
        "work_mode": "scripts/ceo_stdlib_work_mode.py",
    }
    paths = {name: ROOT / rel for name, rel in rels.items()}
    for path in paths.values():
        assert path.is_file(), path

    driver_sha = sha(paths["driver"])
    recipe_sha = sha(paths["recipe"])
    profile_sha = sha(paths["profile"])
    row = {
        "driver_sha256": driver_sha,
        "recipe_sha256": recipe_sha,
        "profile_sha256": profile_sha,
        "canonical_driver_sha256": sha(CANONICAL_DRIVER),
        "canonical_recipe_sha256": sha(CANONICAL_RECIPE),
        "canonical_profile_sha256": sha(CANONICAL_PROFILE),
        "old_driver_sha256": sha(OLD_DRIVER),
        "old_recipe_sha256": sha(OLD_RECIPE),
    }
    print("W13_CANONICAL_HASHES", json.dumps(row, sort_keys=True))
    assert driver_sha == row["canonical_driver_sha256"] != row["old_driver_sha256"], row
    assert recipe_sha == row["canonical_recipe_sha256"] != row["old_recipe_sha256"], row
    assert profile_sha == row["canonical_profile_sha256"], row

    driver = paths["driver"].read_text(encoding="utf-8")
    assert "Wait-DevToolsDown" in driver
    assert "Prune-UnrelatedRestoredTargets" in driver

    provider = paths["provider"].read_text(encoding="utf-8")
    assert 'kind = WorkerKind.BROWSER' in provider
    assert '"api_calls": 0' in provider
    assert '"paid_api_calls": 0' in provider
    assert 'cmd.extend(["-ConversationUrl", str(request.conversation_id)])' in provider
    assert 'cmd.extend(["-ConversationUrl", str(request.conversation_id), "-NoLaunch"])' not in provider

    routing = paths["routing"].read_text(encoding="utf-8")
    assert 'p.kind.value == "browser"' in routing
    assert "browser_first_cold_start" in routing

    work = paths["work_mode"].read_text(encoding="utf-8")
    assert "from ceo_core.providers.chatgpt_web import ChatGPTWebTransport" in work
    assert "self.browser_transport = ChatGPTWebTransport()" in work
    assert 'self.primary_ai_surface = "chatgpt-web"' in work
    assert "self.AIWorkerProvider(self.browser_transport)" in work
    assert "CEO_ALLOW_OPTIONAL_API" in work
    assert "browser_control_verified" in work

    start = method_block(work, "    async def start_project(self, body: dict[str, Any]):")
    assert "IA web no disponible. CEO necesita Chrome/Edge" not in start
    assert "goal_text = str(body.get(\"goal\") or \"\").strip()" in start

    main = work[work.index("def main() -> int:"):]
    assert "_gui_gemini_key_prompt()" not in main
    assert "Modo browser-first: no se solicita ni se necesita ninguna API key." in main
    assert "engine.browser_transport.probe_control()" in main

    contract_path = ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    hashes = dict(contract.get("file_hashes") or {})
    required_raw = contract.get("required_files")
    required = set(required_raw or []) if isinstance(required_raw, list) else None
    for name, rel in rels.items():
        assert hashes.get(rel) == sha(ROOT / rel), (name, rel, hashes.get(rel), sha(ROOT / rel))
        if required is not None:
            assert rel in required, (name, rel)

    browser_builder = (REPO / "ceo-browser" / "build_browser_first_lab.py").read_text(encoding="utf-8")
    assert 'BROWSER_SRC = REPO / "ceo-browser"' in browser_builder
    assert 'CORE_SRC / "browser_ai"' not in browser_builder
    assert 'BROWSER_SRC / "windows_chatgpt_cdp_driver.ps1"' in browser_builder
    assert 'BROWSER_SRC / "recipes" / "chatgpt_web.json"' in browser_builder

    first_trial_builder = (REPO / "ceo-browser" / "build_first_trial_lab.py").read_text(encoding="utf-8")
    assert 'SRC=REPO/"ceo-browser"' in first_trial_builder
    assert 'copy(SRC/rel,ROOT/"ceo_core"/"browser_ai"/rel)' in first_trial_builder

    print("W13_CANONICAL_BROWSER_WORKER_REGRESSION_PASS")


def main() -> int:
    if os.environ.get("CEO_W13_EXPECT_RAW_GAP") == "1":
        raw_case()
    else:
        patched_case()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
