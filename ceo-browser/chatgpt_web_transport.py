from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

from ceo_core.ai_worker import AITransport, AITransportRequest, AITransportResponse
from ceo_core.contracts import ProviderHealth, WorkerKind


class ChatGPTWebTransport(AITransport):
    """Free web-UI transport for CEO.

    This transport does not call the OpenAI API. It controls a local Chrome/Edge
    session through the Windows CDP driver bundled with CEO. The browser profile is
    persistent so the human can log in once and CEO can reuse the session.
    """

    name = "chatgpt-web-free"
    kind = WorkerKind.BROWSER

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        profile_dir: str | Path | None = None,
        timeout_seconds: int = 180,
        port: int = 9227,
        max_prompt_chars: int = 22_000,
    ) -> None:
        package_root = Path(root).resolve() if root else Path(__file__).resolve().parents[1]
        self.root = package_root
        self.driver = package_root / "browser_ai" / "windows_chatgpt_cdp_driver.ps1"
        recipe_override = str(os.environ.get("CEO_BROWSER_RECIPE_PATH") or "").strip()
        self.recipe = Path(recipe_override).expanduser().resolve() if recipe_override else (
            package_root / "browser_ai" / "recipes" / "chatgpt_web.json"
        )
        local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        self.profile_dir = Path(profile_dir).resolve() if profile_dir else local / "CEO de IAs" / "browser-profile"
        self.timeout_seconds = max(30, int(timeout_seconds))
        self.port = int(port)
        self.max_prompt_chars = max(2_000, int(max_prompt_chars))

    @staticmethod
    def _powershell() -> str | None:
        return (
            shutil.which("powershell.exe")
            or shutil.which("pwsh.exe")
            or shutil.which("powershell")
        )

    @staticmethod
    def _browser() -> str | None:
        candidates = [
            Path(os.environ.get("PROGRAMFILES") or "") / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA") or "") / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES") or "") / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]
        for path in candidates:
            if str(path) and path.is_file():
                return str(path)
        return shutil.which("chrome.exe") or shutil.which("msedge.exe")

    def host_ready(self) -> tuple[bool, str]:
        if os.name != "nt":
            return False, "browser worker requires Windows in this build"
        if not self._powershell():
            return False, "PowerShell not found"
        if not self._browser():
            return False, "Chrome/Edge not found"
        if not self.driver.is_file():
            return False, f"browser driver missing: {self.driver}"
        if not self.recipe.is_file():
            return False, f"ChatGPT recipe missing: {self.recipe}"
        return True, "browser host ready; web login may still be required"

    async def healthcheck(self) -> ProviderHealth:
        ready, detail = self.host_ready()
        return ProviderHealth(
            provider=self.name,
            available=ready,
            detail=detail,
            metadata={
                "kind": "browser",
                "api_required": False,
                "paid_api_required": False,
                "persistent_profile": str(self.profile_dir),
                "login_state": "not_probed",
            },
        )

    async def send(self, request: AITransportRequest) -> AITransportResponse:
        prompt = str(request.prompt or "")
        if not prompt.strip():
            raise RuntimeError("browser AI prompt is empty")
        if len(prompt) > self.max_prompt_chars:
            raise RuntimeError(
                f"BROWSER_TASK_TOO_LARGE: prompt_chars={len(prompt)}>{self.max_prompt_chars}; "
                "split the work unit before dispatch"
            )
        ready, detail = self.host_ready()
        if not ready:
            raise RuntimeError(f"BROWSER_UNAVAILABLE: {detail}")

        powershell = self._powershell()
        assert powershell
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        fd, prompt_path_raw = tempfile.mkstemp(prefix="ceo-browser-prompt-", suffix=".txt")
        os.close(fd)
        prompt_path = Path(prompt_path_raw)
        prompt_path.write_text(prompt, encoding="utf-8")

        cmd = [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.driver),
            "-RecipePath",
            str(self.recipe),
            "-PromptFile",
            str(prompt_path),
            "-ProfileDir",
            str(self.profile_dir),
            "-Port",
            str(self.port),
            "-TimeoutSeconds",
            str(self.timeout_seconds),
        ]
        if request.conversation_id:
            cmd.extend(["-ConversationUrl", str(request.conversation_id), "-NoLaunch"])

        try:
            creationflags = getattr(asyncio.subprocess, "CREATE_NO_WINDOW", 0)
            # asyncio.subprocess has no CREATE_NO_WINDOW constant on normal Python;
            # use the subprocess module value when available.
            import subprocess as _subprocess
            creationflags = getattr(_subprocess, "CREATE_NO_WINDOW", 0)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=creationflags,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout_seconds + 30,
            )
        finally:
            prompt_path.unlink(missing_ok=True)

        raw = stdout.decode("utf-8", "replace").strip()
        if not raw:
            detail = stderr.decode("utf-8", "replace")[-1000:]
            raise RuntimeError(f"BROWSER_DRIVER_EMPTY: {detail}")
        try:
            row = json.loads(raw.splitlines()[-1])
        except Exception as exc:
            raise RuntimeError(f"BROWSER_DRIVER_BAD_JSON: {raw[-1000:]}") from exc

        if not isinstance(row, dict) or not row.get("ok"):
            status = str(row.get("status") if isinstance(row, dict) else "ERROR")
            detail = str(row.get("detail") if isinstance(row, dict) else row)
            if status == "LOGIN_OR_UI_REQUIRED":
                raise RuntimeError(
                    "BROWSER_LOGIN_REQUIRED: abre ChatGPT en el perfil de CEO e inicia sesión una vez"
                )
            raise RuntimeError(f"{status}: {detail}")

        text = str(row.get("response") or "").strip()
        if not text:
            raise RuntimeError("BROWSER_EMPTY_RESPONSE")
        return AITransportResponse(
            text=text,
            conversation_id=str(row.get("conversation_url") or request.conversation_id or "") or None,
            usage={
                "api_calls": 0,
                "paid_api_calls": 0,
                "browser_turns": 1,
                "response_chars": int(row.get("response_chars") or len(text)),
            },
            metadata={
                "transport": "chrome-cdp-web-ui",
                "provider_surface": "chatgpt-web",
                "api_required": False,
                "selector": row.get("selector"),
            },
        )
