from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    recipe_path: Path
    profile_dir: Path
    port: int
    physical_verified: bool
    api_required: bool


class BrowserProviderRegistry:
    """Resolve free web-AI providers without coupling CEO to one vendor."""

    def __init__(self, *, base_dir: str | Path, registry_path: str | Path | None = None, base_port: int = 9227):
        self.base_dir = Path(base_dir).resolve()
        self.registry_path = Path(registry_path).resolve() if registry_path else self.base_dir / "provider_registry.json"
        self.base_port = int(base_port)
        row = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(row, dict) or not isinstance(row.get("providers"), dict):
            raise ValueError("invalid provider registry")
        self.row = row
        self.default_order = tuple(str(x) for x in row.get("default_order") or ())
        self.providers = row["providers"]

    @staticmethod
    def default_local_root() -> Path:
        return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")) / "CEO de IAs"

    def resolve(self, name: str, *, local_root: str | Path | None = None) -> ProviderSpec:
        if name not in self.providers:
            raise KeyError(name)
        cfg = self.providers[name]
        local = Path(local_root).resolve() if local_root else self.default_local_root()
        recipe = (self.base_dir / str(cfg["recipe"])).resolve()
        profile = (local / str(cfg["profile"])).resolve()
        return ProviderSpec(
            name=name,
            recipe_path=recipe,
            profile_dir=profile,
            port=self.base_port + int(cfg.get("port_offset") or 0),
            physical_verified=bool(cfg.get("physical_verified")),
            api_required=bool(cfg.get("api_required")),
        )

    def ordered(self, preferred: Iterable[str] | None = None, *, local_root: str | Path | None = None) -> list[ProviderSpec]:
        order = []
        seen = set()
        for name in list(preferred or ()) + list(self.default_order):
            if name in self.providers and name not in seen:
                order.append(self.resolve(name, local_root=local_root))
                seen.add(name)
        return order

    def first_with_existing_session(self, preferred: Iterable[str] | None = None) -> ProviderSpec | None:
        for spec in self.ordered(preferred):
            session = spec.profile_dir / "CEO_BROWSER_SESSION.json"
            if not session.is_file():
                continue
            try:
                row = json.loads(session.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            if isinstance(row, dict) and row.get("ok") and row.get("status") == "SESSION_READY":
                return spec
        return None


def load_default_registry(base_dir: str | Path, *, base_port: int = 9227) -> BrowserProviderRegistry:
    return BrowserProviderRegistry(base_dir=base_dir, base_port=base_port)
