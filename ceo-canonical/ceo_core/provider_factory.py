from __future__ import annotations

import os
from pathlib import Path

from ceo_core.ai_worker import AIWorkerProvider
from ceo_core.browser_worker import BrowserChatConfig, BrowserChatTransport
from ceo_core.contracts import WorkerProvider
from ceo_core.providers.gemini_interactions import GeminiInteractionsTransport
from ceo_core.providers.mock import MockWorkerProvider
from ceo_core.providers.openai_responses import OpenAIResponsesTransport
from ceo_core.provider_secrets import resolve_provider_secret
from ceo_core.self_hosting_tools import ChatGPTWorkerAdapter
from ceo_core.mobile_node import MobileRemoteWorkerProvider


def build_providers(root: Path, data_root: Path | None = None) -> list[WorkerProvider]:
    providers: list[WorkerProvider] = []
    data_root = data_root or (root / "data")
    openai_key = resolve_provider_secret("openai")
    gemini_key = resolve_provider_secret("gemini")
    if openai_key:
        # ChatGPT is a first-class worker while retaining the historical
        # ``openai-responses`` provider name used by routing/portfolio evidence.
        providers.append(ChatGPTWorkerAdapter(OpenAIResponsesTransport(api_key=openai_key)))
    if gemini_key:
        providers.append(AIWorkerProvider(GeminiInteractionsTransport(api_key=gemini_key)))

    mobile_url = os.getenv("CEO_MOBILE_URL", "").strip()
    mobile_secret = os.getenv("CEO_MOBILE_SHARED_SECRET", "").strip()
    if mobile_url and mobile_secret:
        providers.append(MobileRemoteWorkerProvider(mobile_url, mobile_secret))

    # Generic browser provider becomes active only when the user has configured a service URL
    # and selectors. This avoids pretending we can reliably guess third-party web UIs.
    if os.getenv("CEO_BROWSER_START_URL"):
        config = BrowserChatConfig(
            name=os.getenv("CEO_BROWSER_NAME", "browser-chat"),
            start_url=os.environ["CEO_BROWSER_START_URL"],
            input_selector=os.getenv("CEO_BROWSER_INPUT_SELECTOR", "textarea"),
            send_selector=os.getenv("CEO_BROWSER_SEND_SELECTOR", "button[type=submit]"),
            assistant_selector=os.getenv("CEO_BROWSER_ASSISTANT_SELECTOR", "[data-role=assistant]"),
            profile_dir=str(data_root / "browser_profiles" / os.getenv("CEO_BROWSER_NAME", "default")),
            registry_path=str(data_root / "browser_sessions.json"),
            executable_path=os.getenv("CEO_CHROMIUM_EXECUTABLE") or None,
            headless=os.getenv("CEO_BROWSER_HEADLESS", "1") != "0",
            login_selector=os.getenv("CEO_BROWSER_LOGIN_SELECTOR") or None,
            captcha_selector=os.getenv("CEO_BROWSER_CAPTCHA_SELECTOR") or None,
        )
        providers.append(AIWorkerProvider(BrowserChatTransport(config), capabilities=frozenset({"general", "chat", "reasoning", "browser"})))

    if not providers:
        providers.append(MockWorkerProvider())
    return providers
