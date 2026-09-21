from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from first_trial_safety import atomic_json


REQUIRED = {
    "B09_B14_PHYSICAL_GATE.json": {
        "B14_REAL_WEB_TWO_TURN_PASS",
        "B14_REAL_CHATGPT_TWO_TURN_PASS",
    },
    "B15_B18_PHYSICAL_GATE.json": {
        "B18_REAL_BROWSER_ARTIFACT_PASS",
    },
    "B19_B20_CODE_GATE.json": {
        "B20_REAL_WEB_CODE_GATE_PASS",
        "B20_REAL_CHATGPT_CODE_GATE_PASS",
    },
}


def default_evidence_dir() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return local / "CEO de IAs" / "evidence"


def read_json(path: Path) -> dict[str, Any]:
    row = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(row, dict):
        raise ValueError(f"{path.name}: expected JSON object")
    return row


def finalize_field(
    root: str | Path,
    *,
    trial_id: str = "",
    provider: str = "",
    canonical_out: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    checks: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    providers: set[str] = set()

    for name, accepted_statuses in REQUIRED.items():
        path = root / name
        if not path.is_file():
            failures.append(f"missing {name}")
            continue
        try:
            row = read_json(path)
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            continue

        status = str(row.get("status") or "")
        ok = bool(row.get("ok")) and status in accepted_statuses
        if "api_calls" not in row or "paid_api_calls" not in row:
            ok = False
            failures.append(f"{name}: explicit API counters are missing")
        else:
            try:
                if int(row.get("api_calls")) != 0 or int(row.get("paid_api_calls")) != 0:
                    ok = False
                    failures.append(f"{name}: API counter is not zero")
            except Exception:
                ok = False
                failures.append(f"{name}: invalid API counters")

        row_provider = str(row.get("provider") or "").strip()
        if row_provider:
            providers.add(row_provider)
        if not ok:
            failures.append(
                f"{name}: expected one of {sorted(accepted_statuses)}, got {status!r}"
            )
        checks[name] = {
            "ok": ok,
            "status": status,
            "conversation_url": row.get("conversation_url"),
            "provider": row_provider,
        }

    b14_path = root / "B09_B14_PHYSICAL_GATE.json"
    if b14_path.is_file():
        b14 = read_json(b14_path)
        if b14.get("same_conversation") is not True:
            failures.append("B14: same_conversation is not true")

    b18_path = root / "B15_B18_PHYSICAL_GATE.json"
    if b18_path.is_file():
        b18 = read_json(b18_path)
        if b18.get("content_verified") is not True:
            failures.append("B18: artifact content was not verified")
        artifact_raw = str(b18.get("artifact_path") or "").strip()
        artifact_path = Path(artifact_raw) if artifact_raw else None
        if not artifact_path or not artifact_path.is_file():
            failures.append("B18: persisted artifact file is missing")
        else:
            expected_sha = str(b18.get("artifact_sha256") or "")
            actual_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            if not expected_sha or actual_sha != expected_sha:
                failures.append("B18: persisted artifact SHA-256 mismatch")

    b20_path = root / "B19_B20_CODE_GATE.json"
    if b20_path.is_file():
        b20 = read_json(b20_path)
        if b20.get("final_tests_passed") is not True:
            failures.append("B20: final tests did not pass")
        if b20.get("no_commit_push_merge") is not True:
            failures.append("B20: no-commit/push/merge invariant failed")
        if b20.get("source_verified") is not True:
            failures.append("B20: expected source correction missing")

    if len(providers) > 1:
        failures.append(f"provider drift inside one field campaign: {sorted(providers)}")
    selected_provider = provider or (next(iter(providers)) if len(providers) == 1 else "browser-provider-pool")

    verified = (
        not failures
        and len(checks) == len(REQUIRED)
        and all(x["ok"] for x in checks.values())
    )
    state = {
        "schema_version": 2,
        "phase": "B29-B30",
        "trial_id": str(trial_id or ""),
        "evidence_dir": str(root),
        "BROWSER_FIELD_VERIFIED": verified,
        "browser_ai_surface": selected_provider,
        "provider_pool_enabled": True,
        "api_calls_required": 0,
        "physical_gates": checks,
        "failures": failures,
        "next_capability": (
            "isolated real CEO candidate testing"
            if verified
            else "correct the failed phase in this trial only"
        ),
        "production_promotion_allowed": False,
        "automatic_merge_allowed": False,
        "automatic_purchase_allowed": False,
    }
    atomic_json(root / "BROWSER_FIELD_STATE.json", state)
    if canonical_out:
        atomic_json(Path(canonical_out), state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", default=str(default_evidence_dir()))
    parser.add_argument("--trial-id", default="")
    parser.add_argument("--provider", default="")
    parser.add_argument("--canonical-out", default="")
    args = parser.parse_args()
    state = finalize_field(
        args.evidence_dir,
        trial_id=args.trial_id,
        provider=args.provider,
        canonical_out=(args.canonical_out or None),
    )
    print(json.dumps(state, ensure_ascii=False))
    return 0 if state["BROWSER_FIELD_VERIFIED"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
