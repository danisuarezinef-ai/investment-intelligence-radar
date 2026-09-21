from __future__ import annotations

from dataclasses import asdict, dataclass
import re


@dataclass(slots=True)
class ProviderRecoveryDecision:
    category: str
    retry: bool
    retry_after_seconds: int
    rotate_model: bool
    rotate_provider: bool
    requires_human: bool
    spending_allowed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class ProviderResilienceV2:
    """Fail-closed provider retry policy.  Never purchases quota or enables billing."""

    def classify(self, error: str | None, attempt: int = 1) -> ProviderRecoveryDecision:
        text = (error or "").lower()
        attempt = max(1, int(attempt))
        backoff = min(300, 2 ** min(8, attempt))
        if "429" in text or "resource_exhausted" in text or "quota" in text:
            return ProviderRecoveryDecision("quota", True, max(300, backoff), True, True, False)
        if "no provider can execute" in text or "no compatible provider" in text:
            return ProviderRecoveryDecision("provider_unavailable", True, max(300, backoff), False, True, False)
        if any(x in text for x in ("401", "403", "invalid api key", "unauthorized", "permission_denied")):
            return ProviderRecoveryDecision("authentication", False, 0, False, False, True)
        if "404" in text and "model" in text:
            return ProviderRecoveryDecision("model_unavailable", True, 1, True, False, False)
        if any(x in text for x in (
            "timeout", "timed out", "connecterror", "connect error",
            "connection reset", "connection refused", "network is unreachable",
            "name or service not known", "temporary failure in name resolution",
            "temporarily unavailable", "tls", "ssl", "503", "502",
        )):
            return ProviderRecoveryDecision("transient", attempt < 5, backoff, False, attempt >= 3, False)
        if any(x in text for x in ("billing", "payment", "purchase", "credit")):
            return ProviderRecoveryDecision("billing_gate", False, 0, False, False, True)
        return ProviderRecoveryDecision("unknown", attempt < 3, backoff, False, attempt >= 2, attempt >= 3)

    @staticmethod
    def model_candidates(discovered: list[str], failed_model: str | None = None) -> list[str]:
        failed = (failed_model or "").strip()
        preferred = [
            "gemini-3.8-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
        ]
        seen: set[str] = set()
        out: list[str] = []
        for model in preferred + list(discovered):
            m = str(model).strip()
            if not m or m == failed or m in seen:
                continue
            seen.add(m); out.append(m)
        return out
