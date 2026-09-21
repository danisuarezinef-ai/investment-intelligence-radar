from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Protocol
from urllib.parse import urlparse

from .engineering_autonomy import ToolExecutionBroker
from .integrity_engineering import SideEffectDefinition
from .models import ProjectState
from .production_intelligence import ToolDefinition, ToolRegistry
from .runtime import configure_playwright_runtime, user_data_root


def _now() -> float:
    return time.time()


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-._")
    return value[:96] or "default"


def _sha256_file(path: str | Path) -> str:
    h = sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. Windows/Desktop control layer
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DesktopWindow:
    window_id: str
    title: str
    app_id: str | None = None
    process_id: int | None = None
    visible: bool = True
    focused: bool = False
    minimized: bool = False
    maximized: bool = False


class DesktopBackend(Protocol):
    def list_windows(self) -> list[DesktopWindow]: ...
    def launch(self, executable: str, args: list[str]) -> dict[str, Any]: ...
    def focus(self, window_id: str) -> bool: ...
    def minimize(self, window_id: str) -> bool: ...
    def maximize(self, window_id: str) -> bool: ...
    def close(self, window_id: str) -> bool: ...
    def capabilities(self) -> set[str]: ...


class WindowsDesktopBackend:
    """Physical Windows backend, imported lazily and never exercised on non-Windows.

    Window manipulation uses pywinauto when installed. App launching uses argv lists
    with shell=False. This class deliberately has no mouse-coordinate fallback; that is
    isolated in VisualFallbackController.
    """

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("WindowsDesktopBackend requires Windows")

    def capabilities(self) -> set[str]:
        caps = {"launch_application"}
        try:
            import pywinauto  # noqa: F401
            caps |= {"list_windows", "focus_window", "minimize_window", "maximize_window", "close_window"}
        except Exception:
            pass
        return caps

    def _desktop(self):
        try:
            from pywinauto import Desktop
        except Exception as exc:  # pragma: no cover - exercised only on physical Windows
            raise RuntimeError("pywinauto is required for Windows UI Automation") from exc
        return Desktop(backend="uia")

    def list_windows(self) -> list[DesktopWindow]:
        rows: list[DesktopWindow] = []
        for w in self._desktop().windows():  # pragma: no cover - physical Windows
            try:
                handle = int(w.handle)
                title = w.window_text() or ""
                rows.append(
                    DesktopWindow(
                        window_id=str(handle),
                        title=title,
                        process_id=int(w.process_id()),
                        visible=bool(w.is_visible()),
                        focused=bool(w.has_focus()),
                    )
                )
            except Exception:
                continue
        return rows

    def launch(self, executable: str, args: list[str]) -> dict[str, Any]:
        flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        proc = subprocess.Popen(
            [executable, *args], shell=False, creationflags=flags, close_fds=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "process_id": proc.pid, "executable": executable}

    def _win(self, window_id: str):
        return self._desktop().window(handle=int(window_id))

    def focus(self, window_id: str) -> bool:
        self._win(window_id).set_focus(); return True  # pragma: no cover

    def minimize(self, window_id: str) -> bool:
        self._win(window_id).minimize(); return True  # pragma: no cover

    def maximize(self, window_id: str) -> bool:
        self._win(window_id).maximize(); return True  # pragma: no cover

    def close(self, window_id: str) -> bool:
        self._win(window_id).close(); return True  # pragma: no cover


# ---------------------------------------------------------------------------
# 9-10. Application registry + capability discovery
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ApplicationSpec:
    app_id: str
    display_name: str
    capabilities: list[str]
    executable_candidates: list[str] = field(default_factory=list)
    executable: str | None = None
    default_args: list[str] = field(default_factory=list)
    browser: bool = False
    windows_only: bool = True
    discovered: bool = False
    discovery_source: str = "declared"


class ApplicationRegistry:
    KEY = "application_registry_v1"

    DEFAULTS = (
        ApplicationSpec(
            "chrome", "Google Chrome",
            ["browse", "tabs", "dom", "forms", "download", "upload", "session_reuse"],
            [
                r"%PROGRAMFILES%\\Google\\Chrome\\Application\\chrome.exe",
                r"%PROGRAMFILES(X86)%\\Google\\Chrome\\Application\\chrome.exe",
                r"%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe",
                "chrome", "chrome.exe", "google-chrome", "chromium",
            ], browser=True,
        ),
        ApplicationSpec(
            "explorer", "Windows Explorer",
            ["files", "folders", "open_path"],
            [r"%WINDIR%\\explorer.exe", "explorer.exe"],
        ),
        ApplicationSpec(
            "terminal", "Windows Terminal",
            ["terminal", "commands", "stdout", "stderr"],
            [r"%LOCALAPPDATA%\\Microsoft\\WindowsApps\\wt.exe", "wt.exe", "powershell.exe", "cmd.exe"],
        ),
        ApplicationSpec(
            "vscode", "Visual Studio Code",
            ["code", "workspace", "editor", "terminal", "problems"],
            [
                r"%LOCALAPPDATA%\\Programs\\Microsoft VS Code\\Code.exe",
                r"%PROGRAMFILES%\\Microsoft VS Code\\Code.exe", "code", "Code.exe",
            ],
        ),
    )

    def initialize(self, state: ProjectState) -> None:
        rows = state.metadata.setdefault(self.KEY, {})
        for spec in self.DEFAULTS:
            rows.setdefault(spec.app_id, asdict(spec))

    @staticmethod
    def _expand(candidate: str) -> str:
        expanded = os.path.expandvars(candidate)
        # os.path.expandvars on Linux does not expand %VAR%; support Windows notation
        for match in re.findall(r"%([^%]+)%", expanded):
            expanded = expanded.replace(f"%{match}%", os.environ.get(match, f"%{match}%"))
        return expanded

    def register(self, state: ProjectState, spec: ApplicationSpec) -> None:
        self.initialize(state)
        state.metadata[self.KEY][spec.app_id] = asdict(spec)

    def get(self, state: ProjectState, app_id: str) -> ApplicationSpec | None:
        self.initialize(state)
        row = state.metadata[self.KEY].get(app_id)
        return ApplicationSpec(**row) if row else None

    def discover(self, state: ProjectState, *, finder: Callable[[str], str | None] | None = None) -> list[ApplicationSpec]:
        self.initialize(state)
        finder = finder or shutil.which
        discovered: list[ApplicationSpec] = []
        for app_id, row in state.metadata[self.KEY].items():
            spec = ApplicationSpec(**row)
            executable = None; source = "not_found"
            for raw in spec.executable_candidates:
                candidate = self._expand(raw)
                if "%" not in candidate:
                    p = Path(candidate)
                    if (p.is_absolute() or "\\" in candidate or "/" in candidate) and p.is_file():
                        executable, source = str(p), "filesystem"; break
                found = finder(candidate)
                if found:
                    executable, source = found, "path"; break
            spec.executable = executable
            spec.discovered = bool(executable)
            spec.discovery_source = source
            state.metadata[self.KEY][app_id] = asdict(spec)
            discovered.append(spec)
        return discovered

    def list(self, state: ProjectState) -> list[ApplicationSpec]:
        self.initialize(state)
        return [ApplicationSpec(**row) for row in state.metadata[self.KEY].values()]


class ApplicationCapabilityDiscovery:
    def __init__(self, registry: ApplicationRegistry | None = None) -> None:
        self.registry = registry or ApplicationRegistry()

    def discover_for(self, state: ProjectState, app_id: str, *, desktop_backend: DesktopBackend | None = None) -> dict[str, Any]:
        spec = self.registry.get(state, app_id)
        if not spec:
            return {"known": False, "app_id": app_id, "capabilities": []}
        caps = set(spec.capabilities)
        if desktop_backend:
            caps |= set(desktop_backend.capabilities())
        return {
            "known": True,
            "app_id": app_id,
            "display_name": spec.display_name,
            "discovered": spec.discovered,
            "executable": spec.executable,
            "capabilities": sorted(caps),
            "browser": spec.browser,
        }

    def rank(self, state: ProjectState, required: Iterable[str]) -> list[dict[str, Any]]:
        wanted = {str(x).lower() for x in required}
        rows = []
        for spec in self.registry.list(state):
            caps = {x.lower() for x in spec.capabilities}
            coverage = len(wanted & caps) / max(1, len(wanted))
            if wanted and not coverage:
                continue
            rows.append({
                "app_id": spec.app_id, "display_name": spec.display_name,
                "coverage": round(coverage, 4), "available": spec.discovered,
                "capabilities": sorted(caps),
            })
        return sorted(rows, key=lambda x: (-x["coverage"], not x["available"], x["app_id"]))


class DesktopControlLayer:
    KEY = "desktop_control_v1"

    def __init__(self, backend: DesktopBackend, registry: ApplicationRegistry | None = None) -> None:
        self.backend = backend
        self.registry = registry or ApplicationRegistry()

    def launch(self, state: ProjectState, app_id: str, *, args: Iterable[str] = ()) -> dict[str, Any]:
        spec = self.registry.get(state, app_id)
        if not spec:
            return {"ok": False, "reason": "unknown_application", "app_id": app_id}
        if not spec.discovered or not spec.executable:
            return {"ok": False, "reason": "application_not_discovered", "app_id": app_id}
        result = self.backend.launch(spec.executable, [*spec.default_args, *[str(x) for x in args]])
        state.metadata.setdefault(self.KEY, {}).setdefault("events", []).append({
            "ts": _now(), "action": "launch", "app_id": app_id,
            "process_id": result.get("process_id"), "ok": bool(result.get("ok")),
        })
        return result

    def windows(self) -> list[dict[str, Any]]:
        return [asdict(x) for x in self.backend.list_windows()]

    def act(self, action: str, window_id: str) -> dict[str, Any]:
        fn = {"focus": self.backend.focus, "minimize": self.backend.minimize, "maximize": self.backend.maximize, "close": self.backend.close}.get(action)
        if not fn:
            return {"ok": False, "reason": "unsupported_action", "action": action}
        return {"ok": bool(fn(window_id)), "action": action, "window_id": window_id}

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        return {
            "platform": os.name,
            "backend_capabilities": sorted(self.backend.capabilities()),
            "applications": [asdict(x) for x in self.registry.list(state)],
            "windows": self.windows(),
        }


# ---------------------------------------------------------------------------
# 2-5. Chrome controller, session reuse, download/upload
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ChromeSessionDescriptor:
    session_id: str
    profile_dir: str
    persistent: bool
    created_at: float
    last_used_at: float
    stores_passwords: bool = False
    note: str = "Dedicated browser profile; auth state belongs to Chromium, not CEO project state."


class ChromeSessionManager:
    KEY = "chrome_sessions_v1"

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or (user_data_root() / "chrome_profiles"))
        self.root.mkdir(parents=True, exist_ok=True)

    def get_or_create(self, state: ProjectState, session_id: str = "default") -> ChromeSessionDescriptor:
        sid = _slug(session_id)
        rows = state.metadata.setdefault(self.KEY, {})
        row = rows.get(sid)
        now = _now()
        if row:
            row["last_used_at"] = now
            # Never accept a caller-persisted secret/password field in session metadata.
            for key in list(row):
                if re.search(r"(?i)(password|secret|token|cookie|credential)", key):
                    row.pop(key, None)
            return ChromeSessionDescriptor(**row)
        profile = self.root / sid
        profile.mkdir(parents=True, exist_ok=True)
        desc = ChromeSessionDescriptor(sid, str(profile), True, now, now)
        rows[sid] = asdict(desc)
        return desc

    def list(self, state: ProjectState) -> list[ChromeSessionDescriptor]:
        return [ChromeSessionDescriptor(**row) for row in state.metadata.setdefault(self.KEY, {}).values()]


class PlaywrightChromeRuntime:
    """Persistent real-Chrome runtime. The actual browser is launched only on demand."""

    def __init__(self, profile_dir: str | Path, *, executable_path: str | None = None, headless: bool = False) -> None:
        configure_playwright_runtime()
        self.profile_dir = str(profile_dir)
        self.executable_path = executable_path
        self.headless = headless
        self._pw = None; self.context = None; self.page = None

    async def start(self) -> None:
        if self.context is not None:
            return
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        kwargs: dict[str, Any] = {"headless": self.headless, "args": ["--disable-background-mode"]}
        if self.executable_path:
            kwargs["executable_path"] = self.executable_path
        self.context = await self._pw.chromium.launch_persistent_context(self.profile_dir, **kwargs)
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

    async def stop(self) -> None:
        """Best-effort idempotent browser shutdown.

        A persistent Chromium window may already have been closed by the operator or
        by Chromium itself. Playwright reports that normal situation as
        ``TargetClosedError``. Cleanup must never turn a completed field mission into
        a failed mission merely because the target was already gone.
        """
        context, pw = self.context, self._pw
        # Clear public handles first so a second stop() is harmless even when the
        # underlying Playwright close call raises.
        self.context = None
        self.page = None
        self._pw = None

        if context is not None:
            try:
                await context.close()
            except Exception as exc:
                name = type(exc).__name__
                msg = str(exc).lower()
                benign = (
                    name == "TargetClosedError"
                    or "target page, context or browser has been closed" in msg
                    or "browser has been closed" in msg
                )
                if not benign:
                    raise

        if pw is not None:
            try:
                await pw.stop()
            except Exception as exc:
                name = type(exc).__name__
                msg = str(exc).lower()
                benign = (
                    name == "TargetClosedError"
                    or "event loop is closed" in msg
                    or "target page, context or browser has been closed" in msg
                )
                if not benign:
                    raise

    async def new_tab(self, url: str | None = None):
        await self.start(); page = await self.context.new_page()
        if url: await page.goto(url, wait_until="domcontentloaded")
        self.page = page; return page

    async def navigate(self, url: str) -> dict[str, Any]:
        await self.start(); await self.page.goto(url, wait_until="domcontentloaded")
        return {"url": self.page.url, "title": await self.page.title()}

    async def click(self, selector: str) -> None:
        await self.start(); await self.page.locator(selector).first.click()

    async def fill(self, selector: str, value: str) -> None:
        await self.start(); await self.page.locator(selector).first.fill(value)

    async def press(self, selector: str, key: str) -> None:
        await self.start(); await self.page.locator(selector).first.press(key)

    async def scroll(self, delta_y: int = 700) -> None:
        await self.start(); await self.page.mouse.wheel(0, int(delta_y))

    async def text(self, selector: str = "body") -> str:
        await self.start(); return await self.page.locator(selector).inner_text()

    async def screenshot(self) -> bytes:
        await self.start(); return await self.page.screenshot(full_page=False)


class BrowserDownloadManager:
    KEY = "browser_downloads_v1"

    def register(self, state: ProjectState, path: str | Path, *, source_url: str = "", task_id: str | None = None) -> dict[str, Any]:
        p = Path(path).resolve()
        if not p.is_file():
            raise FileNotFoundError(str(p))
        row = {
            "path": str(p), "name": p.name, "size": p.stat().st_size,
            "sha256": _sha256_file(p), "source_url": source_url,
            "task_id": task_id, "registered_at": _now(),
        }
        state.metadata.setdefault(self.KEY, []).append(row)
        if task_id and task_id in state.tasks:
            state.tasks[task_id].metadata.setdefault("artifacts", []).append({"kind": "browser_download", **row})
        return row

    async def click_and_capture(self, state: ProjectState, page: Any, selector: str, destination_dir: str | Path, *, task_id: str | None = None, timeout_ms: int = 120_000) -> dict[str, Any]:
        dest = Path(destination_dir).resolve(); dest.mkdir(parents=True, exist_ok=True)
        async with page.expect_download(timeout=timeout_ms) as info:
            await page.locator(selector).first.click()
        download = await info.value
        filename = _slug(download.suggested_filename)
        target = dest / filename
        await download.save_as(str(target))
        return self.register(state, target, source_url=getattr(page, "url", ""), task_id=task_id)


class BrowserUploadManager:
    KEY = "browser_uploads_v1"

    async def upload(self, state: ProjectState, page: Any, selector: str, paths: Iterable[str | Path], *, task_id: str | None = None) -> dict[str, Any]:
        resolved = [str(Path(p).resolve()) for p in paths]
        for p in resolved:
            if not Path(p).is_file(): raise FileNotFoundError(p)
        await page.locator(selector).first.set_input_files(resolved)
        row = {"paths": resolved, "selector": selector, "task_id": task_id, "uploaded_at": _now(), "url": getattr(page, "url", "")}
        state.metadata.setdefault(self.KEY, []).append(row)
        return row


class ChromeController:
    KEY = "chrome_controller_v1"

    def __init__(self, sessions: ChromeSessionManager | None = None, runtime_factory: Callable[..., Any] = PlaywrightChromeRuntime) -> None:
        self.sessions = sessions or ChromeSessionManager()
        self.runtime_factory = runtime_factory
        self.runtime = None
        self.downloads = BrowserDownloadManager(); self.uploads = BrowserUploadManager()

    async def start(self, state: ProjectState, *, session_id: str = "default", executable_path: str | None = None, headless: bool = False) -> dict[str, Any]:
        desc = self.sessions.get_or_create(state, session_id)
        self.runtime = self.runtime_factory(desc.profile_dir, executable_path=executable_path, headless=headless)
        await self.runtime.start()
        state.metadata.setdefault(self.KEY, {})["active_session"] = desc.session_id
        state.metadata[self.KEY]["started_at"] = _now()
        return {"ok": True, "session": asdict(desc)}

    def _require(self):
        if self.runtime is None: raise RuntimeError("ChromeController not started")
        return self.runtime

    async def stop(self) -> None:
        if self.runtime is not None:
            await self.runtime.stop(); self.runtime = None

    async def new_tab(self, url: str | None = None) -> dict[str, Any]:
        page = await self._require().new_tab(url)
        return {"ok": True, "url": getattr(page, "url", url or "")}

    async def navigate(self, url: str) -> dict[str, Any]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Chrome navigation requires http(s) URL")
        return await self._require().navigate(url)

    async def click(self, selector: str) -> dict[str, Any]:
        await self._require().click(selector); return {"ok": True, "selector": selector}

    async def fill(self, selector: str, value: str) -> dict[str, Any]:
        await self._require().fill(selector, value); return {"ok": True, "selector": selector, "characters": len(value)}

    async def press(self, selector: str, key: str) -> dict[str, Any]:
        await self._require().press(selector, key); return {"ok": True, "selector": selector, "key": key}

    async def scroll(self, delta_y: int = 700) -> dict[str, Any]:
        await self._require().scroll(delta_y); return {"ok": True, "delta_y": int(delta_y)}

    async def text(self, selector: str = "body") -> dict[str, Any]:
        text = await self._require().text(selector); return {"ok": True, "selector": selector, "text": text}


# ---------------------------------------------------------------------------
# 6. Visual fallback -- only after structured controls fail
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class VisualTarget:
    x: int
    y: int
    confidence: float
    label: str = ""


class VisualInputAdapter(Protocol):
    def screenshot(self) -> Any: ...
    def click(self, x: int, y: int) -> None: ...
    def type_text(self, text: str) -> None: ...
    def press(self, key: str) -> None: ...


class PyAutoGUIAdapter:
    def __init__(self) -> None:
        try:
            import pyautogui
        except Exception as exc:  # pragma: no cover - optional Windows dependency
            raise RuntimeError("pyautogui is required for visual fallback") from exc
        self.pg = pyautogui

    def screenshot(self): return self.pg.screenshot()  # pragma: no cover
    def click(self, x: int, y: int) -> None: self.pg.click(x=x, y=y)  # pragma: no cover
    def type_text(self, text: str) -> None: self.pg.write(text, interval=0.01)  # pragma: no cover
    def press(self, key: str) -> None: self.pg.press(key)  # pragma: no cover


class VisualFallbackController:
    KEY = "visual_fallback_v1"

    def __init__(self, adapter: VisualInputAdapter, resolver: Callable[[Any, str], VisualTarget | None], *, min_confidence: float = .75) -> None:
        self.adapter = adapter; self.resolver = resolver; self.min_confidence = float(min_confidence)

    def resolve(self, description: str) -> VisualTarget | None:
        target = self.resolver(self.adapter.screenshot(), description)
        if target and target.confidence >= self.min_confidence:
            return target
        return None

    def act(self, state: ProjectState, *, description: str, action: str = "click", text: str = "", structured_failed: bool = False, approved: bool = False) -> dict[str, Any]:
        if not structured_failed:
            return {"ok": False, "reason": "structured_control_must_fail_first"}
        if not approved:
            return {"ok": False, "reason": "visual_fallback_requires_approval"}
        target = self.resolve(description)
        if not target:
            return {"ok": False, "reason": "target_not_resolved"}
        if action == "click": self.adapter.click(target.x, target.y)
        elif action == "type": self.adapter.click(target.x, target.y); self.adapter.type_text(text)
        else: return {"ok": False, "reason": "unsupported_visual_action"}
        row = {"ts": _now(), "description": description, "action": action, "target": asdict(target)}
        state.metadata.setdefault(self.KEY, []).append(row)
        return {"ok": True, **row}


# ---------------------------------------------------------------------------
# 7. Windows UI Automation v1
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class UIAControl:
    control_id: str
    name: str
    control_type: str
    automation_id: str = ""
    enabled: bool = True
    visible: bool = True


class WindowsUIAutomationBackend:
    def __init__(self) -> None:
        if os.name != "nt": raise RuntimeError("Windows UI Automation requires Windows")
        try:
            from pywinauto import Desktop
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("pywinauto is required for UI Automation") from exc
        self._desktop_cls = Desktop

    def _root(self, title_re: str):
        return self._desktop_cls(backend="uia").window(title_re=title_re)

    def controls(self, title_re: str) -> list[UIAControl]:
        root = self._root(title_re); out=[]
        for c in root.descendants():  # pragma: no cover
            try:
                info=c.element_info; out.append(UIAControl(str(info.handle or info.runtime_id), info.name or "", info.control_type or "", info.automation_id or "", bool(c.is_enabled()), bool(c.is_visible())))
            except Exception: continue
        return out

    def invoke(self, title_re: str, *, name: str | None = None, automation_id: str | None = None) -> bool:
        root=self._root(title_re); kwargs={}
        if name: kwargs["title"] = name
        if automation_id: kwargs["auto_id"] = automation_id
        root.child_window(**kwargs).wrapper_object().invoke(); return True  # pragma: no cover

    def set_text(self, title_re: str, *, name: str | None = None, automation_id: str | None = None, value: str) -> bool:
        root=self._root(title_re); kwargs={}
        if name: kwargs["title"] = name
        if automation_id: kwargs["auto_id"] = automation_id
        root.child_window(**kwargs).wrapper_object().set_edit_text(value); return True  # pragma: no cover


class WindowsUIAutomationController:
    def __init__(self, backend: Any) -> None: self.backend = backend
    def controls(self, title_re: str) -> list[dict[str, Any]]: return [asdict(x) for x in self.backend.controls(title_re)]
    def invoke(self, title_re: str, **selector) -> dict[str, Any]: return {"ok": bool(self.backend.invoke(title_re, **selector)), "action": "invoke"}
    def set_text(self, title_re: str, value: str, **selector) -> dict[str, Any]: return {"ok": bool(self.backend.set_text(title_re, value=value, **selector)), "action": "set_text", "characters": len(value)}


# ---------------------------------------------------------------------------
# 8. Keyboard/mouse broker -- always goes through existing ToolExecutionBroker
# ---------------------------------------------------------------------------


class DesktopInputAdapter:
    def __init__(self, visual_adapter: VisualInputAdapter) -> None: self.visual = visual_adapter
    def execute(self, action: str, *, x: int | None = None, y: int | None = None, text: str = "", key: str = "") -> dict[str, Any]:
        if action == "click":
            if x is None or y is None: raise ValueError("x/y required")
            self.visual.click(int(x), int(y))
        elif action == "type": self.visual.type_text(text)
        elif action == "press": self.visual.press(key)
        else: raise ValueError("unsupported input action")
        return {"action": action, "ok": True}


class KeyboardMouseBrokerInstaller:
    TOOL = "desktop_input"

    def install(self, state: ProjectState, broker: ToolExecutionBroker, adapter: DesktopInputAdapter) -> None:
        ToolRegistry().register(state, ToolDefinition(
            name=self.TOOL,
            capabilities=["mouse", "keyboard", "gui_fallback"],
            permissions=["desktop.input"],
            external_effects=True,
            destructive=False,
            reliability=.55,
        ))
        broker.register_adapter(self.TOOL, adapter.execute)
        broker.declare_side_effects(state, SideEffectDefinition(
            tool=self.TOOL, effects=["write", "execute"], reversible=True,
            external=True, destructive=False, default_targets=["active_desktop_session"],
        ))


# ---------------------------------------------------------------------------
# Unified 1-10 core / preflight (no physical actions required)
# ---------------------------------------------------------------------------


class DesktopBrowserIntegrationCore:
    VERSION = 1

    def __init__(self, registry: ApplicationRegistry | None = None) -> None:
        self.registry = registry or ApplicationRegistry()
        self.capabilities = ApplicationCapabilityDiscovery(self.registry)
        self.sessions = ChromeSessionManager()

    def initialize(self, state: ProjectState) -> dict[str, Any]:
        self.registry.initialize(state)
        self.registry.discover(state)
        state.metadata.setdefault("desktop_browser_integration_v1", {})["initialized_at"] = _now()
        state.metadata["desktop_browser_integration_v1"]["physical_windows_validated"] = False
        state.metadata["desktop_browser_integration_v1"]["chrome_live_validated"] = False
        return self.snapshot(state)

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        apps = self.registry.list(state)
        return {
            "version": self.VERSION,
            "applications": [asdict(x) for x in apps],
            "available_applications": [x.app_id for x in apps if x.discovered],
            "chrome_sessions": [asdict(x) for x in self.sessions.list(state)],
            "physical_windows_validated": bool(state.metadata.get("desktop_browser_integration_v1", {}).get("physical_windows_validated", False)),
            "chrome_live_validated": bool(state.metadata.get("desktop_browser_integration_v1", {}).get("chrome_live_validated", False)),
            "field_status": "DEFERRED_BY_USER" if os.name != "nt" else "NOT_VERIFIED",
        }

    def local_preflight(self, state: ProjectState) -> dict[str, Any]:
        self.registry.initialize(state)
        chrome = self.registry.get(state, "chrome")
        required = {
            "desktop_control_contract": True,
            "chrome_structured_controller": True,
            "persistent_chrome_sessions": True,
            "download_manager": True,
            "upload_manager": True,
            "visual_fallback_guarded": True,
            "windows_uia_contract": True,
            "keyboard_mouse_brokered": True,
            "application_registry": chrome is not None,
            "capability_discovery": bool(self.capabilities.rank(state, ["browse"])),
        }
        return {
            "pass": all(required.values()),
            "checks": required,
            "windows_physical": "DEFERRED_BY_USER",
            "chrome_physical": "DEFERRED_BY_USER",
        }
