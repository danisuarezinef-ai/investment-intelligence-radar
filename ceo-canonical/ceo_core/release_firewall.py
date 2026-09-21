from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ReleaseFirewallReport:
    allowed: bool
    channel: str
    release_status: str
    problems: tuple[str, ...]
    qualification: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReleaseQualificationFirewall:
    """Fail-closed production publication firewall.

    A locally tested candidate is not a stable release. Stable publication requires
    explicit physical/runtime evidence. Missing flags are failures, never implicit
    permission. This guard is intentionally duplicated at coordinator and publisher
    boundaries so CI, activators and prepared-release bridges cannot bypass it.
    """

    LOCAL_REQUIRED = (
        "tests_passed",
        "security_passed",
        "clean_extract_passed",
        "package_contract_passed",
    )

    PHYSICAL_REQUIRED = (
        "windows_stage_preflight_passed",
        "windows_install_passed",
        "windows_restart_reopen_passed",
        "windows_rollback_passed",
        "provider_persistence_passed",
        "field_validation_passed",
    )

    @classmethod
    def evaluate(
        cls,
        qualification: dict[str, Any] | None,
        *,
        channel: str,
        release_status: str,
    ) -> ReleaseFirewallReport:
        q = dict(qualification or {})
        problems: list[str] = []
        for flag in cls.LOCAL_REQUIRED:
            if q.get(flag) is not True:
                problems.append(f"{flag}!=true")
        if int(q.get("failed_tests") or 0) != 0:
            problems.append("failed_tests>0")
        if int(q.get("security_findings") or 0) != 0:
            problems.append("security_findings>0")

        stable = str(channel or "").lower() == "stable" or str(release_status or "").lower() == "release"
        if stable:
            if q.get("production_ready") is not True:
                problems.append("production_ready!=true")
            if q.get("field_validation_pending") is not False:
                problems.append("field_validation_pending!=false")
            for flag in cls.PHYSICAL_REQUIRED:
                if q.get(flag) is not True:
                    problems.append(f"{flag}!=true")

        return ReleaseFirewallReport(
            allowed=not problems,
            channel=str(channel or ""),
            release_status=str(release_status or ""),
            problems=tuple(problems),
            qualification=q,
        )

    @classmethod
    def require_stable(cls, qualification: dict[str, Any] | None) -> None:
        report = cls.evaluate(qualification, channel="stable", release_status="release")
        if not report.allowed:
            raise PermissionError(
                "stable release blocked by production firewall: " + "; ".join(report.problems)
            )
