from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BrowserAdapter:
    name: str
    start_url: str
    input_selector: str
    send_selector: str
    assistant_selector: str
    login_selector: str | None = None
    captcha_selector: str | None = None
    capabilities: tuple[str, ...] = ("general", "chat", "browser")


class AdapterRegistry:
    def __init__(self) -> None:
        self._items: dict[str, BrowserAdapter] = {}

    def register(self, adapter: BrowserAdapter) -> None:
        self._items[adapter.name] = adapter

    def get(self, name: str) -> BrowserAdapter:
        if name not in self._items:
            raise KeyError(name)
        return self._items[name]

    def list(self) -> list[str]:
        return sorted(self._items)
