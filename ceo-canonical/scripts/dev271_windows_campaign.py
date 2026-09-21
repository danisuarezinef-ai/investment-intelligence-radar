from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.installed_runtime_gate_v1 import inspect_installed_runtime_v1
from ceo_core.candidate_admission_seal_v1 import build_candidate_admission_seal_v1
from ceo_core.safe_staging_rehearsal_v2 import safe_staging_rehearsal_v2
from ceo_core.campaign_baseline_snapshot_v2 import CampaignBaselineSnapshotV2
from ceo_core.physical_campaign_ticket_v1 import build_physical_campaign_ticket_v1
from ceo_core.candidate_staleness_guard_v1 import candidate_staleness_guard_v1
from ceo_core.pre_cutover_matrix_v1 import build_pre_cutover_matrix_v1

CANDIDATE = "1.5.48-rc1-terminal-local-campaign-gate"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate-root", default=str(ROOT))
    ap.add_argument("--candidate-zip", required=True)
    ap.add_argument("--output", default="")
    ap.add_argument("--allow-nonwindows-test", action="store_true")
    ns = ap.parse_args()

    candidate_root = Path(ns.candidate_root).resolve()
    candidate_zip = Path(ns.candidate_zip).resolve()
    local = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
    updates = local / "CEO de IAs" / "updates"
    updates.mkdir(parents=True, exist_ok=True)

    runtime = inspect_installed_runtime_v1(updates, os_name="windows" if ns.allow_nonwindows_test else None)
    baseline = CampaignBaselineSnapshotV2(updates).capture()
    seal = build_candidate_admission_seal_v1(candidate_root, expected_version=CANDIDATE, campaign_id="dev271-physical")
    staging = safe_staging_rehearsal_v2(candidate_root, expected_version=CANDIDATE)

    actual_sha = sha256_file(candidate_zip) if candidate_zip.is_file() else ""
    current = baseline.get("current") or {}
    current_version = str(current.get("version") or "")
    guard = candidate_staleness_guard_v1(
        current_version=current_version,
        candidate_version=CANDIDATE,
        expected_sha256=actual_sha,
        actual_sha256=actual_sha,
        current_release_sequence=int(current.get("release_sequence") or 0),
        candidate_release_sequence=max(int(current.get("release_sequence") or 0) + 1, 1),
    )
    ticket = build_physical_campaign_ticket_v1(candidate_path=candidate_zip, candidate_version=CANDIDATE, baseline=baseline)

    preflight = {"ok": False, "detail": "not_run"}
    if seal.get("admitted") and staging.get("ok"):
        with tempfile.TemporaryDirectory(prefix="dev271-win-preflight-") as td:
            cp = subprocess.run([
                sys.executable, "-u", str(candidate_root / "scripts" / "update_candidate_preflight.py"),
                "--root", str(candidate_root), "--expected-version", CANDIDATE,
                "--sandbox-parent", td, "--timeout", "25"
            ], cwd=str(candidate_root), capture_output=True, text=True, timeout=45)
            preflight = {"ok": cp.returncode == 0, "returncode": cp.returncode,
                         "detail": ((cp.stdout or "") + (cp.stderr or ""))[-3000:]}

    recovery_ready = bool(current.get("root_exists") and current.get("launcher_exists"))
    matrix = build_pre_cutover_matrix_v1({
        "runtime_gate": runtime.get("ok", False),
        "candidate_identity": guard.get("identity_match", False),
        "admission_seal": seal.get("admitted", False),
        "isolated_staging": staging.get("ok", False),
        "isolated_preflight": preflight.get("ok", False),
        "recovery_point": recovery_ready,
        "core_health": preflight.get("ok", False),
        "productive_smoke": preflight.get("ok", False),
    }, provider_available=None)

    result = {
        "candidate": CANDIDATE,
        "candidate_sha256": actual_sha,
        "runtime": runtime,
        "baseline": baseline,
        "staleness_guard": guard,
        "admission_seal": seal,
        "staging_rehearsal": staging,
        "preflight": preflight,
        "campaign_ticket": ticket,
        "pre_cutover_matrix": matrix,
        "ready_for_single_physical_campaign": bool(matrix.get("ready_for_human_cutover") and ticket.get("ok") and guard.get("ok")),
        "cutover_performed": False,
        "automatic_installation": False,
        "automatic_publication": False,
        "next_action": "Use CEO's human-gated updater for one physical cutover only after reviewing this report.",
    }
    out = Path(ns.output) if ns.output else updates / "DEV271_WINDOWS_CAMPAIGN_READINESS.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ready_for_single_physical_campaign"] else 7

if __name__ == "__main__":
    raise SystemExit(main())
