from __future__ import annotations

import re
from typing import Any


def _version_key(value: str) -> tuple[Any, ...]:
    text = (value or "0").strip().lower()
    base_text, sep, suffix = text.partition("-")
    nums = [int(x) for x in re.findall(r"\d+", base_text)] or [0]
    base = tuple((nums + [0, 0, 0, 0])[:4])
    if not sep or not suffix:
        return (*base, 1, 99, 0, "")
    phase_rank = 2
    phase_num = 0
    m = re.search(r"(?:^|[-_.])(dev|alpha|a|beta|b|rc)(\d*)", suffix)
    if m:
        phase_rank = {"dev": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "rc": 3}[m.group(1)]
        phase_num = int(m.group(2) or 0)
    return (*base, 0, phase_rank, phase_num, suffix)


def candidate_staleness_guard_v1(*, current_version: str, candidate_version: str,
                                 expected_sha256: str, actual_sha256: str,
                                 current_release_sequence: int = 0,
                                 candidate_release_sequence: int = 0) -> dict[str, Any]:
    problems: list[str] = []
    exp = str(expected_sha256 or "").strip().lower()
    got = str(actual_sha256 or "").strip().lower()
    if len(exp) != 64 or any(c not in "0123456789abcdef" for c in exp):
        problems.append("expected_sha256_invalid")
    elif got != exp:
        problems.append("candidate_sha256_mismatch")
    if current_version and _version_key(candidate_version) <= _version_key(current_version):
        problems.append("candidate_not_newer")
    if int(current_release_sequence or 0) and int(candidate_release_sequence or 0):
        if int(candidate_release_sequence) <= int(current_release_sequence):
            problems.append("release_sequence_not_newer")
    return {
        "ok": not problems,
        "problems": problems,
        "current_version": current_version,
        "candidate_version": candidate_version,
        "downgrade_blocked": "candidate_not_newer" in problems,
        "stale_sequence_blocked": "release_sequence_not_newer" in problems,
        "identity_match": "candidate_sha256_mismatch" not in problems and "expected_sha256_invalid" not in problems,
    }
