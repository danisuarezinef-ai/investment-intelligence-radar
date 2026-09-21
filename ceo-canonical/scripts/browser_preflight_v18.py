from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

CSS_CANDIDATES = [
    "#prompt-textarea",
    "[data-testid='prompt-textarea']",
    "div.ProseMirror[contenteditable='true']",
    "[contenteditable='true'][role='textbox']",
    "form [contenteditable='true']",
    "textarea[placeholder]",
    "textarea",
    "div[contenteditable='true']",
]

async def visible_candidate(page):
    for selector in CSS_CANDIDATES:
        try:
            loc = page.locator(selector)
            count = await loc.count()
            for i in range(count):
                node = loc.nth(i)
                if await node.is_visible():
                    # Prefer nodes that are actually editable. is_editable is not supported by every
                    # contenteditable variant, so visibility + editable-ish attributes are accepted.
                    try:
                        editable = await node.is_editable()
                    except Exception:
                        editable = False
                    ce = await node.get_attribute("contenteditable")
                    if editable or ce == "true" or selector.startswith("textarea"):
                        return selector, i
        except Exception:
            continue
    return None, None

async def main() -> int:
    from playwright.async_api import async_playwright

    out = Path(os.environ["CEO_VALIDATION_OUT"])
    out.mkdir(parents=True, exist_ok=True)
    name = os.getenv("CEO_BROWSER_NAME", "chatgpt-browser-live")
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home()/"AppData"/"Local")))
    profile = local / "CEO de IAs" / "browser_profiles" / name
    exe = os.getenv("CEO_CHROMIUM_EXECUTABLE")
    report = {
        "profile": str(profile), "executable": exe, "composer_visible": False,
        "selector": None, "selector_index": None, "url": None, "title": None,
        "error": None, "wait_seconds": 0, "login_text_detected": False,
    }
    try:
        async with async_playwright() as p:
            kw = {"headless": False}
            if exe:
                kw["executable_path"] = exe
            ctx = await p.chromium.launch_persistent_context(str(profile), **kw)
            try:
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
                # ChatGPT is React-heavy and the composer can appear well after DOMContentLoaded.
                # Poll for up to 90 seconds instead of taking an immediate snapshot.
                for sec in range(91):
                    report["url"] = page.url
                    try:
                        report["title"] = await page.title()
                    except Exception:
                        pass
                    selector, idx = await visible_candidate(page)
                    if selector:
                        report["composer_visible"] = True
                        report["selector"] = selector
                        report["selector_index"] = idx
                        report["wait_seconds"] = sec
                        break
                    if sec in (5, 15, 30, 60):
                        try:
                            body = (await page.locator("body").inner_text()).lower()
                            report["login_text_detected"] = any(x in body for x in ("log in", "sign in", "iniciar sesión", "inicia sesión"))
                        except Exception:
                            pass
                    await page.wait_for_timeout(1000)

                if report["composer_visible"]:
                    (out / "composer_selector_v18.txt").write_text(report["selector"], encoding="utf-8")
                else:
                    # Preserve enough diagnostics to fix the next issue without guessing.
                    try:
                        await page.screenshot(path=str(out / "BROWSER_PREFLIGHT_V18.png"), full_page=True)
                    except Exception:
                        pass
                    try:
                        html = await page.content()
                        (out / "BROWSER_PREFLIGHT_V18.html").write_text(html, encoding="utf-8")
                    except Exception:
                        pass
            finally:
                await ctx.close()
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"

    (out / "BROWSER_PREFLIGHT_V18.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if report["composer_visible"]:
        print(f"[PASS] Preflight: compositor visible tras {report['wait_seconds']} s con {report['selector']}")
        return 0
    print("[FAIL] Preflight: no se encontro un compositor visible tras 90 s.")
    print(json.dumps(report, ensure_ascii=False))
    print("Se guardaron BROWSER_PREFLIGHT_V18.png/html para diagnostico.")
    return 1

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
