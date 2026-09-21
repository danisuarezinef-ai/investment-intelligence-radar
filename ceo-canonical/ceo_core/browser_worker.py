from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ceo_core.ai_worker import AITransport, AITransportRequest, AITransportResponse
from ceo_core.contracts import ProviderHealth, WorkerKind
from ceo_core.session_store import JsonSessionStore
from ceo_core.runtime import configure_playwright_runtime


@dataclass(slots=True)
class BrowserChatConfig:
    name: str
    start_url: str
    input_selector: str
    send_selector: str
    assistant_selector: str
    profile_dir: str
    registry_path: str = "data/browser_sessions.json"
    executable_path: str | None = None
    headless: bool = True
    response_timeout_ms: int = 120_000
    bootstrap_html: str | None = None
    login_selector: str | None = None
    captcha_selector: str | None = None


class BrowserChatTransport(AITransport):
    """Generic persistent Playwright chat transport.

    A service-specific adapter only needs stable selectors and a start URL. Auth cookies,
    local storage and other browser state live in the persistent profile directory.
    """

    kind = WorkerKind.BROWSER

    def __init__(self, config: BrowserChatConfig) -> None:
        configure_playwright_runtime()
        self.config = config
        self.name = config.name
        self.profile_dir = Path(config.profile_dir)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.sessions = JsonSessionStore(config.registry_path)
        # Chromium forbids concurrent use of one user-data-dir. Scale browser workers by
        # creating multiple transports/profiles rather than sharing this lock.
        self._profile_lock = asyncio.Lock()

    async def send(self, request: AITransportRequest) -> AITransportResponse:
        """Send one turn through a persistent browser profile.

        Real Chrome/Edge on Windows can briefly keep the user-data-dir locked while a
        previous persistent context is shutting down. In that case Playwright may raise
        ``TargetClosedError`` during navigation or while waiting for the composer. Retry
        the *whole browser turn* with bounded backoff instead of converting this transient
        browser-lifecycle race into a provider failure.
        """
        last_exc: BaseException | None = None
        # Three attempts are bounded and deliberately short; scheduler-level retry remains
        # available for genuine provider failures.
        for attempt in range(1, 4):
            try:
                return await self._send_once(request)
            except Exception as exc:
                is_target_closed = (
                    type(exc).__name__ == "TargetClosedError"
                    or "Target page, context or browser has been closed" in str(exc)
                    or "Target page, context or browser has been closed" in repr(exc)
                )
                if not is_target_closed:
                    raise
                last_exc = exc
                if attempt >= 3:
                    raise
                await asyncio.sleep(1.5 * attempt)
        assert last_exc is not None
        raise last_exc

    async def _send_once(self, request: AITransportRequest) -> AITransportResponse:
        from playwright.async_api import async_playwright

        session_id = request.conversation_id or f"browser-{uuid4().hex}"
        saved = self.sessions.get(session_id) or {}
        url = saved.get("url") or self.config.start_url

        async with self._profile_lock:
            async with async_playwright() as p:
                launch_kwargs = {
                    "headless": self.config.headless,
                    # Prevent a system Chrome/Edge background process from keeping the
                    # dedicated CEO profile alive after context.close().
                    "args": ["--disable-background-mode"],
                }
                if self.config.executable_path:
                    launch_kwargs["executable_path"] = self.config.executable_path
                context = await p.chromium.launch_persistent_context(
                    str(self.profile_dir),
                    **launch_kwargs,
                )
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=self.config.response_timeout_ms)
                    if self.config.bootstrap_html is not None:
                        await page.set_content(self.config.bootstrap_html)
                    if self.config.captcha_selector and await page.locator(self.config.captcha_selector).count():
                        return AITransportResponse(
                            text='<CEO_RESULT>{"status":"escalate","reason":"CAPTCHA requires human intervention","requires_user":true,"decision_title":"Complete CAPTCHA","decision_options":["I completed the CAPTCHA","Keep paused"],"recommendation":"I completed the CAPTCHA"}</CEO_RESULT>',
                            conversation_id=session_id, metadata={"needs_user":"captcha","url":page.url}
                        )
                    if self.config.login_selector and await page.locator(self.config.login_selector).count():
                        return AITransportResponse(
                            text='<CEO_RESULT>{"status":"escalate","reason":"Authentication requires human intervention","requires_user":true,"decision_title":"Sign in to service","decision_options":["I signed in","Keep paused"],"recommendation":"I signed in"}</CEO_RESULT>',
                            conversation_id=session_id, metadata={"needs_user":"login","url":page.url}
                        )
                    async def first_visible(selector: str):
                        loc = page.locator(selector)
                        count = await loc.count()
                        for idx in range(count):
                            candidate = loc.nth(idx)
                            try:
                                if await candidate.is_visible():
                                    return candidate
                            except Exception:
                                continue
                        return loc.first

                    # ChatGPT and other browser providers change DOM wrappers frequently.
                    # Keep the configured selector as the primary contract, but use several
                    # conservative response fallbacks before declaring the provider broken.
                    assistant_selectors = []
                    for selector in (
                        self.config.assistant_selector,
                        "[data-message-author-role='assistant']",
                        "article[data-testid^='conversation-turn-'] [data-message-author-role='assistant']",
                        "[data-testid='conversation-turn-assistant']",
                    ):
                        if selector and selector not in assistant_selectors:
                            assistant_selectors.append(selector)
                    article_selector = "article[data-testid^='conversation-turn-']"
                    user_selector = "[data-message-author-role='user']"
                    copy_selector = "button[data-testid='copy-turn-action-button'],button[aria-label*='Copy'],button[aria-label*='Copiar']"

                    assistant_before = {selector: await page.locator(selector).count() for selector in assistant_selectors}
                    article_before = await page.locator(article_selector).count()
                    user_before = await page.locator(user_selector).count()
                    copy_before = await page.locator(copy_selector).count()
                    url_before = page.url

                    composer = await first_visible(self.config.input_selector)
                    await composer.wait_for(state="visible", timeout=self.config.response_timeout_ms)
                    try:
                        await composer.fill(request.prompt)
                    except Exception:
                        await composer.click()
                        await page.keyboard.press("Control+A")
                        await page.keyboard.insert_text(request.prompt)

                    sent = False
                    try:
                        send = await first_visible(self.config.send_selector)
                        if await send.is_visible() and await send.is_enabled():
                            await send.click()
                            sent = True
                    except Exception:
                        sent = False
                    if not sent:
                        await composer.press("Enter")

                    # First establish that the UI accepted the outbound message. This avoids
                    # spending the entire response timeout waiting for an assistant selector
                    # when Enter merely inserted a newline or a send click was ignored.
                    ack_deadline = asyncio.get_running_loop().time() + min(20.0, self.config.response_timeout_ms / 1000)
                    send_ack = False
                    while asyncio.get_running_loop().time() < ack_deadline:
                        try:
                            user_now = await page.locator(user_selector).count()
                            article_now = await page.locator(article_selector).count()
                            assistant_ack = False
                            for selector in assistant_selectors:
                                try:
                                    if await page.locator(selector).count() > assistant_before.get(selector, 0):
                                        assistant_ack = True
                                        break
                                except Exception:
                                    continue
                            if user_now > user_before or article_now > article_before or assistant_ack or page.url != url_before:
                                send_ack = True
                                break
                            try:
                                value = await composer.input_value()
                                if request.prompt and value == "":
                                    send_ack = True
                                    break
                            except Exception:
                                try:
                                    current_text = (await composer.inner_text()).strip()
                                    if request.prompt and not current_text:
                                        send_ack = True
                                        break
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        await asyncio.sleep(0.25)
                    if not send_ack:
                        raise TimeoutError("Browser UI did not acknowledge the outbound message within 20s.")

                    async def latest_response_candidate():
                        # 1) Preferred: a genuinely new assistant-specific element.
                        for selector in assistant_selectors:
                            loc = page.locator(selector)
                            try:
                                count = await loc.count()
                            except Exception:
                                continue
                            if count > assistant_before.get(selector, 0):
                                for idx in range(count - 1, assistant_before.get(selector, 0) - 1, -1):
                                    node = loc.nth(idx)
                                    try:
                                        if await node.is_visible():
                                            txt = (await node.inner_text()).strip()
                                            if txt:
                                                return node, txt, selector
                                    except Exception:
                                        continue

                        # 2) Current ChatGPT often wraps user+assistant turns in sequential
                        # article[data-testid^=conversation-turn-] nodes. Require two new
                        # articles so the newly-added user prompt cannot be mistaken for the
                        # assistant response.
                        articles = page.locator(article_selector)
                        try:
                            acount = await articles.count()
                        except Exception:
                            acount = 0
                        if acount >= article_before + 2:
                            node = articles.last
                            try:
                                if await node.is_visible():
                                    txt = (await node.inner_text()).strip()
                                    if txt and txt not in request.prompt:
                                        return node, txt, article_selector
                            except Exception:
                                pass

                        # 3) A newly-created copy action is a useful semantic signal that an
                        # assistant response exists even if the wrapper attributes changed.
                        copies = page.locator(copy_selector)
                        try:
                            ccount = await copies.count()
                        except Exception:
                            ccount = 0
                        if ccount > copy_before and acount > article_before:
                            node = articles.last
                            try:
                                txt = (await node.inner_text()).strip()
                                if txt:
                                    return node, txt, copy_selector
                            except Exception:
                                pass
                        return None, "", None

                    deadline = asyncio.get_running_loop().time() + (self.config.response_timeout_ms / 1000)
                    text = ""
                    stable = 0
                    previous = None
                    response_node = None
                    response_source = None
                    while asyncio.get_running_loop().time() < deadline:
                        node, current, source = await latest_response_candidate()
                        if current:
                            response_node = node
                            response_source = source
                            if current == previous:
                                stable += 1
                            else:
                                stable = 0
                            text = current
                            if "</CEO_RESULT>" in current and stable >= 1:
                                break
                            if stable >= 4:
                                break
                            previous = current
                        await asyncio.sleep(0.6)

                    if not text:
                        # Preserve a more actionable failure than Locator.wait_for on one
                        # brittle selector. The live harness can persist this exact error.
                        raise TimeoutError(
                            "No assistant response was detected before timeout; outbound message was acknowledged, "
                            f"assistant_selectors={assistant_selectors!r}, articles_before={article_before}, "
                            f"articles_after={await page.locator(article_selector).count()}, copies_before={copy_before}, "
                            f"copies_after={await page.locator(copy_selector).count()}"
                        )
                    final_url = page.url
                    self.sessions.put(session_id, {"url": final_url, "name": self.name})
                finally:
                    await context.close()
                    # Give Chrome/Edge on Windows time to release SingletonLock and profile
                    # files before the next autonomous turn reopens the same profile.
                    await asyncio.sleep(1.25)

        return AITransportResponse(
            text=text,
            conversation_id=session_id,
            metadata={"url": final_url, "browser_profile": str(self.profile_dir), "response_source": response_source},
        )

    async def healthcheck(self) -> ProviderHealth:
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                kwargs = {"headless": True}
                if self.config.executable_path:
                    kwargs["executable_path"] = self.config.executable_path
                browser = await p.chromium.launch(**kwargs)
                await browser.close()
            return ProviderHealth(provider=self.name, available=True, detail="Chromium launch succeeded.")
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(provider=self.name, available=False, detail=f"{type(exc).__name__}: {exc}")


async def smoke_open_page(url: str = "https://example.com", executable_path: str | None = None) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        kwargs = {"headless": True}
        if executable_path:
            kwargs["executable_path"] = executable_path
        browser = await p.chromium.launch(**kwargs)
        page = await browser.new_page()
        await page.goto(url)
        title = await page.title()
        await browser.close()
        return title
