from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class SecretSettings:
    """Environment-only secret loader. Secret values are excluded from repr."""
    openai_api_key: str | None = field(default=None, repr=False)
    gemini_api_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "SecretSettings":
        return cls(openai_api_key=os.getenv("OPENAI_API_KEY") or None, gemini_api_key=os.getenv("GEMINI_API_KEY") or None)

    def configured(self) -> list[str]:
        out=[]
        if self.openai_api_key: out.append("openai")
        if self.gemini_api_key: out.append("gemini")
        return out
