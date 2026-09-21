from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.ai_worker import AITransportRequest
from ceo_core.desktop_integration import ApplicationRegistry, ChromeController, WindowsDesktopBackend
from ceo_core.models import ProjectState
from ceo_core.providers.openai_responses import OpenAIResponsesTransport
from ceo_core.self_hosting_tools import TerminalController

OUT = ROOT / "reports" / "SELF_HOSTING_41_50_WINDOWS_FIELD_REPORT.json"


async def main() -> int:
    report = {
        "validator": "self_hosting_41_50_windows_field",
        "windows": "NOT_VERIFIED",
        "chrome_real": "NOT_VERIFIED",
        "multi_app_real": "NOT_VERIFIED",
        "chatgpt_real": "NOT_VERIFIED",
        "errors": [],
    }
    if os.name != "nt":
        report["errors"].append("This validator must be run on physical Windows")
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    state = ProjectState(goal="Validate Self-Hosting Alpha field gates")
    try:
        backend = WindowsDesktopBackend()
        backend.list_windows()
        report["windows"] = "VERIFIED"
    except Exception as exc:
        report["errors"].append(f"windows:{type(exc).__name__}:{exc}")

    registry = ApplicationRegistry(); registry.initialize(state); registry.discover(state)
    chrome = registry.get(state, "chrome")
    page_text = ""
    if chrome and chrome.discovered and chrome.executable:
        controller = ChromeController()
        try:
            await controller.start(state, session_id="self-hosting-alpha", executable_path=chrome.executable, headless=False)
            nav = await controller.navigate("https://example.com")
            text = await controller.text("body")
            page_text = text.get("text", "")
            if nav.get("url", "").startswith("https://example.com") and page_text:
                report["chrome_real"] = "VERIFIED"
        except Exception as exc:
            report["errors"].append(f"chrome:{type(exc).__name__}:{exc}")
        finally:
            try: await controller.stop()
            except Exception: pass
    else:
        report["errors"].append("chrome:not_discovered")

    if report["chrome_real"] == "VERIFIED":
        try:
            with tempfile.TemporaryDirectory(prefix="ceo-alpha-field-") as td:
                root = Path(td)
                artifact = root / "browser.txt"
                artifact.write_text(page_text, encoding="utf-8")
                terminal = TerminalController(root, allowed={Path(sys.executable).name})
                result = terminal.run([sys.executable, "-c", "from pathlib import Path; print(len(Path('browser.txt').read_text()))"])
                if result.ok and result.stdout.strip().isdigit():
                    report["multi_app_real"] = "VERIFIED"
        except Exception as exc:
            report["errors"].append(f"multi_app:{type(exc).__name__}:{exc}")

    transport = OpenAIResponsesTransport()
    try:
        probe = await transport.probe_live()
        if probe.get("ok"):
            response = await transport.send(AITransportRequest(prompt="Return exactly: CEO_ALPHA_WORKER_OK"))
            if "CEO_ALPHA_WORKER_OK" in response.text:
                report["chatgpt_real"] = "VERIFIED"
                report["openai_response_id"] = response.conversation_id
        else:
            report["errors"].append(f"openai_probe:{probe.get('reason','failed')}")
    except Exception as exc:
        report["errors"].append(f"chatgpt:{type(exc).__name__}:{exc}")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(report[x] == "VERIFIED" for x in ("windows", "chrome_real", "multi_app_real", "chatgpt_real")) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
