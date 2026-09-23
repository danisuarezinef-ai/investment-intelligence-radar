from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil


REPO = pathlib.Path(__file__).resolve().parents[1]
BRIDGE = REPO / "ceo-updates" / "dev313-inspect-routing"
BROWSER = REPO / "ceo-browser"

PRODUCTION_SOURCES = {
    "ceo_core/routing.py": BRIDGE / "routing.py",
    "ceo_core/providers/chatgpt_web.py": BRIDGE / "providers" / "chatgpt_web.py",
    "ceo_core/browser_ai/windows_chatgpt_cdp_driver.ps1": BROWSER / "windows_chatgpt_cdp_driver.ps1",
    "ceo_core/browser_ai/open_chatgpt_profile.ps1": BROWSER / "open_chatgpt_profile.ps1",
    "ceo_core/browser_ai/recipes/chatgpt_web.json": BROWSER / "recipes" / "chatgpt_web.json",
}


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
        "        from ceo_core.project_catalog import ProjectCatalog\n"
        "        from ceo_core.providers.gemini_interactions import GeminiInteractionsTransport\n",
        "        from ceo_core.project_catalog import ProjectCatalog\n"
        "        from ceo_core.providers.chatgpt_web import ChatGPTWebTransport\n"
        "        from ceo_core.providers.gemini_interactions import GeminiInteractionsTransport\n",
        "W13 browser provider import",
    )

    text = replace_once(
        text,
        "        self.parse_local_finite_file_goal = parse_local_finite_file_goal\n"
        "        self.GeminiInteractionsTransport = GeminiInteractionsTransport\n"
        "        self.data_dir = user_data_root()\n",
        "        self.parse_local_finite_file_goal = parse_local_finite_file_goal\n"
        "        self.ChatGPTWebTransport = ChatGPTWebTransport\n"
        "        self.browser_transport = ChatGPTWebTransport()\n"
        "        self.browser_provider_ready, self.browser_provider_detail = self.browser_transport.host_ready()\n"
        "        self.browser_control_verified = False\n"
        "        self.browser_control_probe = {}\n"
        "        self.no_api_required = True\n"
        "        self.primary_ai_surface = \"chatgpt-web\"\n"
        "        self.GeminiInteractionsTransport = GeminiInteractionsTransport\n"
        "        self.data_dir = user_data_root()\n",
        "W13 browser transport bindings",
    )

    old_init = (
        "        self.gemini_key = self._pending_gemini_key if startup_trust else None\n"
        "        self.execution_enabled = False\n"
        "        self.provider_mode = (\n"
        "            \"gemini-authenticated-waiting\"\n"
        "            if startup_trust\n"
        "            else (\"gemini-key-pending-validation\" if self._pending_gemini_key else \"plan-only (sin Gemini)\")\n"
        "        )\n"
    )
    new_init = (
        "        self.gemini_key = self._pending_gemini_key if startup_trust else None\n"
        "        self.execution_enabled = bool(self.browser_provider_ready)\n"
        "        self.provider_mode = (\n"
        "            \"browser-provider-ready\"\n"
        "            if self.browser_provider_ready\n"
        "            else (\n"
        "                \"gemini-authenticated-waiting\"\n"
        "                if startup_trust\n"
        "                else (\"gemini-key-pending-validation\" if self._pending_gemini_key else \"browser-unavailable\")\n"
        "            )\n"
        "        )\n"
    )
    text = replace_once(text, old_init, new_init, "W13 browser-first initial state")

    old_router = (
        "    def _router(self):\n"
        "        local_goal_lock = self.GoalLockLocalProviderV1()\n"
        "        local_finite_file = self.LocalFiniteFileProviderV1()\n"
        "        providers = [local_goal_lock, local_finite_file]\n"
        "        if self.execution_enabled and self.gemini_key:\n"
        "            transport = self.GeminiInteractionsTransport(api_key=self.gemini_key, model=self.gemini_model or \"auto\")\n"
        "            providers.insert(0, self.AIWorkerProvider(transport))\n"
        "        return self.MultiProviderRouter(providers)\n"
    )
    new_router = (
        "    def _router(self):\n"
        "        local_goal_lock = self.GoalLockLocalProviderV1()\n"
        "        local_finite_file = self.LocalFiniteFileProviderV1()\n"
        "        providers = [local_goal_lock, local_finite_file]\n"
        "\n"
        "        # W13: Browser Worker is the default external AI surface. The local\n"
        "        # core remains available even when Chrome/session access is unavailable.\n"
        "        self.browser_provider_ready, self.browser_provider_detail = self.browser_transport.host_ready()\n"
        "        if self.browser_provider_ready:\n"
        "            providers.insert(0, self.AIWorkerProvider(self.browser_transport))\n"
        "\n"
        "        # API transports remain opt-in accelerators and are never required.\n"
        "        allow_optional_api = str(os.environ.get(\"CEO_ALLOW_OPTIONAL_API\", \"\")).strip().lower() in {\"1\", \"true\", \"yes\", \"on\"}\n"
        "        if allow_optional_api and self.gemini_key:\n"
        "            transport = self.GeminiInteractionsTransport(api_key=self.gemini_key, model=self.gemini_model or \"auto\")\n"
        "            providers.insert(0, self.AIWorkerProvider(transport))\n"
        "\n"
        "        self.execution_enabled = bool(self.browser_provider_ready or (allow_optional_api and self.gemini_key))\n"
        "        if self.browser_provider_ready:\n"
        "            self.provider_mode = \"browser-provider-ready\"\n"
        "        return self.MultiProviderRouter(providers)\n"
    )
    text = replace_once(text, old_router, new_router, "W13 router")

    # Browser execution must not be disabled merely because optional Gemini fails.
    text = text.replace(
        "                self.execution_enabled = False\n"
        "                self.gemini_key_status = status\n"
        "                self.provider_mode = \"gemini-validation-failed\"\n",
        "                self.execution_enabled = bool(self.browser_provider_ready)\n"
        "                self.gemini_key_status = status\n"
        "                self.provider_mode = \"browser-provider-ready\" if self.browser_provider_ready else \"gemini-validation-failed\"\n",
        1,
    )
    text = text.replace(
        "            self.execution_enabled = False\n"
        "            self.gemini_model = str(probe.get(\"model\") or \"\") or None\n"
        "            self.provider_mode = \"gemini-authenticated-waiting\"\n",
        "            self.execution_enabled = bool(self.browser_provider_ready)\n"
        "            self.gemini_model = str(probe.get(\"model\") or \"\") or None\n"
        "            self.provider_mode = \"browser-provider-ready\" if self.browser_provider_ready else \"gemini-authenticated-waiting\"\n",
        1,
    )
    text = text.replace(
        "        self.provider_mode = \"gemini-live-verified\"\n",
        "        self.provider_mode = \"browser-provider-ready\" if self.browser_provider_ready else \"gemini-live-verified\"\n",
        1,
    )

    # Snapshot exposes browser state to the existing local UI. There are exactly two
    # state dictionaries (no active project / active project).
    snapshot_anchor = '                "provider_mode": self.provider_mode,\n'
    if text.count(snapshot_anchor) != 1:
        raise RuntimeError(f"W13 inactive snapshot anchor count={text.count(snapshot_anchor)}")
    text = text.replace(
        snapshot_anchor,
        snapshot_anchor
        + '                "no_api_required": True,\n'
        + '                "primary_ai_surface": self.primary_ai_surface,\n'
        + '                "browser_provider_ready": self.browser_provider_ready,\n'
        + '                "browser_provider_detail": self.browser_provider_detail,\n'
        + '                "browser_control_verified": self.browser_control_verified,\n'
        + '                "browser_control_probe": dict(self.browser_control_probe or {}),\n',
        1,
    )
    active_anchor = '            "provider_mode": self.provider_mode,\n'
    if text.count(active_anchor) < 1:
        raise RuntimeError("W13 active snapshot anchor missing")
    # Replace the first remaining less-indented snapshot provider_mode occurrence.
    text = text.replace(
        active_anchor,
        active_anchor
        + '            "no_api_required": True,\n'
        + '            "primary_ai_surface": self.primary_ai_surface,\n'
        + '            "browser_provider_ready": self.browser_provider_ready,\n'
        + '            "browser_provider_detail": self.browser_provider_detail,\n'
        + '            "browser_control_verified": self.browser_control_verified,\n'
        + '            "browser_control_probe": dict(self.browser_control_probe or {}),\n',
        1,
    )

    # Browser-first startup: no API prompt unless the operator explicitly opts in.
    main_start = text.index("def main() -> int:")
    key_start = text.index('    key = _normalize_gemini_key(os.environ.get("GEMINI_API_KEY"))\n', main_start)
    try_start = text.index("    try:\n        engine = CEOEngine(key or None)\n", key_start)
    key_block = (
        '    allow_optional_api = str(os.environ.get("CEO_ALLOW_OPTIONAL_API", "")).strip().lower() in {"1", "true", "yes", "on"}\n'
        '    key = None\n'
        '    key_source = "disabled"\n'
        '    if allow_optional_api:\n'
        '        key = _normalize_gemini_key(os.environ.get("GEMINI_API_KEY"))\n'
        '        key_source = "environment" if key else None\n'
        '        key_in_browser = os.getenv("CEO_KEY_IN_BROWSER", "").strip() == "1"\n'
        '        if not key and not key_in_browser:\n'
        '            key = _load_windows_dpapi_gemini_key()\n'
        '            if key:\n'
        '                key_source = "windows-dpapi"\n'
        '        if not key and not key_in_browser:\n'
        '            key = _read_windows_clipboard_gemini_key()\n'
        '            if key:\n'
        '                key_source = "windows-clipboard"\n'
        '        if not key and not key_in_browser:\n'
        '            print("[INFO] API opcional habilitada pero sin clave Gemini; CEO seguirá usando IA web.")\n'
        '    else:\n'
        '        print("[OK] Modo browser-first: no se solicita ni se necesita ninguna API key.")\n'
    )
    text = text[:key_start] + key_block + text[try_start:]

    engine_anchor = "        engine = CEOEngine(key or None)\n        Handler.engine = engine\n"
    engine_insert = (
        "        engine = CEOEngine(key or None)\n"
        "\n"
        "        # W13: prove control of the canonical browser driver when possible,\n"
        "        # but never make core startup depend on Chrome/login availability.\n"
        "        try:\n"
        "            browser_probe = engine.call(engine.browser_transport.probe_control(), timeout=45)\n"
        "        except Exception as browser_exc:\n"
        "            browser_probe = {\n"
        "                \"ok\": False,\n"
        "                \"status\": \"BROWSER_CONTROL_FAILED\",\n"
        "                \"detail\": f\"{type(browser_exc).__name__}: {browser_exc}\"[:900],\n"
        "            }\n"
        "        engine.browser_control_probe = dict(browser_probe or {})\n"
        "        engine.browser_control_verified = bool(\n"
        "            isinstance(browser_probe, dict)\n"
        "            and browser_probe.get(\"ok\") is True\n"
        "            and browser_probe.get(\"status\") == \"BROWSER_CONTROL_READY\"\n"
        "        )\n"
        "        engine.browser_provider_ready = bool(engine.browser_control_verified)\n"
        "        engine.browser_provider_detail = (\n"
        "            \"Chrome/Edge localizado y controlado mediante CDP.\"\n"
        "            if engine.browser_control_verified\n"
        "            else str((browser_probe or {}).get(\"detail\") or \"Browser Worker no disponible todavía.\")\n"
        "        )\n"
        "        engine.execution_enabled = bool(engine.browser_control_verified or (allow_optional_api and engine.gemini_key))\n"
        "        if engine.browser_control_verified:\n"
        "            engine.provider_mode = \"browser-control-verified\"\n"
        "\n"
        "        Handler.engine = engine\n"
    )
    text = replace_once(text, engine_anchor, engine_insert, "W13 startup browser probe")

    text = replace_once(
        text,
        "        provider_validation_started = engine.start_provider_validation_background()\n",
        "        provider_validation_started = engine.start_provider_validation_background() if allow_optional_api else False\n",
        "W13 optional API validation",
    )

    # Do not print Gemini as the reason execution is unavailable in browser-first mode.
    diag_anchor = '        print(f"[OK] Diagnostico persistente: {DIAGNOSTICS.latest_path}")\n'
    diag_pos = text.index(diag_anchor, main_start) + len(diag_anchor)
    keep_open = text.index('        print("Mant', diag_pos)
    text = (
        text[:diag_pos]
        + '        if engine.browser_control_verified:\n'
          '            print("[OK] Browser Worker canónico controlando Chrome/Edge. API requerida: NO.")\n'
          '        elif engine.execution_enabled:\n'
          '            print("[OK] Ejecución externa disponible mediante transporte opcional.")\n'
          '        else:\n'
          '            print("[AVISO] Browser Worker no disponible ahora; el Goal Engine puede crear y persistir objetivos sin perderlos.")\n'
        + text[keep_open:]
    )

    path.write_text(text, encoding="utf-8")


def apply(root: pathlib.Path) -> dict:
    root = root.resolve()

    copied: dict[str, str] = {}
    for relative, source in PRODUCTION_SOURCES.items():
        if not source.is_file():
            raise RuntimeError(f"missing W13 source: {source}")
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[relative] = sha256_file(target)

    work_mode_rel = "scripts/ceo_stdlib_work_mode.py"
    work_mode = root / work_mode_rel
    patch_work_mode(work_mode)
    copied[work_mode_rel] = sha256_file(work_mode)

    contract_path = root / "CEO_UPDATE_PACKAGE.json"
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        hashes = dict(contract.get("file_hashes") or {})
        for relative, digest in copied.items():
            hashes[relative] = digest
        contract["file_hashes"] = hashes
        required = contract.get("required_files")
        if isinstance(required, list):
            for relative in copied:
                if relative not in required:
                    required.append(relative)
        contract_path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return {
        "ok": True,
        "canonical_browser_commit": "c210b93167361b3ff4017368ac2d790fca8de5b3",
        "copied": copied,
        "stale_bridge_browser_ai_used": False,
        "stable_channel_modified": False,
    }


def main() -> int:
    raw = str(os.environ.get("CEO_W13_ROOT") or "").strip()
    if not raw:
        raise RuntimeError("CEO_W13_ROOT is required")
    row = apply(pathlib.Path(raw))
    print("W13_CANONICAL_BROWSER_WORKER_APPLIED")
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
