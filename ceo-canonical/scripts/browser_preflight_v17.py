from __future__ import annotations

import asyncio, json, os
from pathlib import Path

async def main() -> int:
    from playwright.async_api import async_playwright
    out = Path(os.environ["CEO_VALIDATION_OUT"])
    name = os.getenv("CEO_BROWSER_NAME", "chatgpt-browser-live")
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home()/"AppData"/"Local")))
    profile = local / "CEO de IAs" / "browser_profiles" / name
    exe = os.getenv("CEO_CHROMIUM_EXECUTABLE")
    selector = os.getenv("CEO_BROWSER_INPUT_SELECTOR", "#prompt-textarea,div[contenteditable='true']")
    report={"profile":str(profile),"executable":exe,"composer_visible":False,"url":None,"title":None,"error":None}
    try:
        async with async_playwright() as p:
            kw={"headless":False}
            if exe: kw["executable_path"]=exe
            ctx=await p.chromium.launch_persistent_context(str(profile), **kw)
            try:
                page=ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
                report["url"]=page.url
                report["title"]=await page.title()
                loc=page.locator(selector)
                count=await loc.count()
                for i in range(count):
                    try:
                        if await loc.nth(i).is_visible():
                            report["composer_visible"]=True
                            break
                    except Exception:
                        pass
            finally:
                await ctx.close()
    except Exception as exc:
        report["error"]=f"{type(exc).__name__}: {exc}"
    (out/"BROWSER_PREFLIGHT_V17.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    if report["composer_visible"]:
        print("[PASS] Preflight: compositor de ChatGPT visible en el MISMO perfil.")
        return 0
    print("[FAIL] Preflight: no se encontro un compositor visible.")
    print(json.dumps(report,ensure_ascii=False))
    return 1

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
