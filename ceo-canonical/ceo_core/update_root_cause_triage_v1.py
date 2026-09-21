from __future__ import annotations

from typing import Any


class UpdateRootCauseTriageV1:
    RULES = (
        ("candidate_identity", ("sha256_mismatch", "size_mismatch", "signature", "contract", "hash:")),
        ("provider_degraded", ("http 429", "quota", "http 404", "gemini", "provider")),
        ("download_transport", ("download", "urlopen", "connection", "dns", "offline")),
        ("preflight", ("preflight", "sandbox")),
        ("rollback", ("rollback", "previous_pointer", "fallback")),
        ("core_startup", ("exited early", "core_health_timeout", "status_url", "health")),
    )

    def classify(self, evidence: dict[str, Any]) -> dict[str, Any]:
        phase = str(evidence.get("phase") or "").lower()
        reason = str(evidence.get("reason") or evidence.get("outcome") or "").lower()
        text = f"{phase} {reason}"
        category = "unknown"
        for name, needles in self.RULES:
            if any(n in text for n in needles):
                category = name
                break
        provider_only = category == "provider_degraded"
        action = {
            "candidate_identity": "reject_candidate_before_cutover",
            "download_transport": "keep_current_version_and_retry_transport_later",
            "preflight": "reject_candidate_before_cutover",
            "core_startup": "automatic_rollback_and_preserve_evidence",
            "provider_degraded": "keep_core_running_in_degraded_mode",
            "rollback": "stop_campaign_and_require_manual_recovery_review",
            "unknown": "stop_campaign_and_preserve_evidence",
        }[category]
        return {
            "category": category,
            "provider_only": provider_only,
            "core_should_remain_healthy": provider_only,
            "recommended_action": action,
            "automatic_patch_chain": False,
        }
