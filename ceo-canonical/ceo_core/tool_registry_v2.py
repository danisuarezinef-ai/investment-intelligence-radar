from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    capabilities: tuple[str, ...]
    side_effect: str = "none"  # none | reversible | external | destructive
    executable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToolRegistryV2:
    """Declarative capability registry. No arbitrary command fallback exists."""

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not spec.name or spec.name in {"shell", "cmd", "powershell", "arbitrary_command"}:
            raise ValueError("unsafe or invalid tool name")
        self._tools[spec.name] = spec

    def resolve(self, required: list[str], *, human_approved: bool = False) -> list[ToolSpec]:
        req = {str(x) for x in required}
        rows = []
        for spec in self._tools.values():
            if not req.issubset(set(spec.capabilities)):
                continue
            if spec.side_effect in {"external", "destructive"} and not human_approved:
                continue
            rows.append(spec)
        return sorted(rows, key=lambda x: (x.side_effect != "none", x.name))

    def snapshot(self) -> list[dict[str, Any]]:
        return [self._tools[k].to_dict() for k in sorted(self._tools)]
