from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "ceo-android-app"
SCHEMAS = ROOT / "ceo-canonical" / "schemas"
DEV21 = SCHEMAS / "android_dev21"


def load(path: Path) -> dict:
    row = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(row, dict), path
    return row


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    freeze = load(APP / "M01_PROJECT_FREEZE.json")
    inventory = load(APP / "M01_ANDROID_INVENTORY.json")
    recovery = load(APP / "M01_RECOVERY_MATRIX.json")
    baseline = load(APP / "M01_RECOVERED_BASELINE.json")
    master = load(APP / "ANDROID_MASTER_STATE.json")
    manifest = load(DEV21 / "BUILD_PAYLOAD_MANIFEST.json")
    clean = load(DEV21 / "DEV21_CLEAN_VALIDATION.json")
    inputs = load(SCHEMAS / "ANDROID_BUILD_INPUTS_DEV21.json")
    lock = load(DEV21 / "TOOLCHAIN.lock.json")

    assert freeze["active_project"] == "CEO App Android"
    assert freeze["active_branch"] == "ceo-android-first-install"
    assert freeze["reference_roots_read_only"] is True
    assert freeze["installation_policy"]["physical_phone_installation_blocked_until"] == "APP220 / M25"
    assert freeze["installation_policy"]["no_manual_apk_downloads_after_first_install"] is True
    assert "CEO Windows" in freeze["frozen_projects"]
    assert "Radar de inversión" in freeze["frozen_projects"]

    files = manifest.get("files")
    assert isinstance(files, list) and len(files) == 45
    assert sum(int(x["size"]) for x in files) == 152062
    assert all(re.fullmatch(r"[0-9a-f]{64}", str(x["sha256"])) for x in files)
    assert len({x["path"] for x in files}) == 45

    assert recovery["expected_files"] == 45
    assert recovery["recovered_source_files"] == 1
    assert recovery["hash_only_or_reference_files"] == 44
    assert recovery["source_project_recovery_complete"] is False
    recovered = [x for x in recovery["files"] if x["source_content_recovered"]]
    assert [x["path"] for x in recovered] == ["TOOLCHAIN.lock.json"]
    assert recovered[0]["recovered_locations"] == [
        "ceo-canonical/schemas/android_dev21/TOOLCHAIN.lock.json"
    ]

    # No hidden Gradle/Kotlin source is allowed to be mistaken for recovered source.
    source_patterns = ("*.kt", "*.kts")
    materialized = []
    for pattern in source_patterns:
        materialized += [
            p for p in ROOT.rglob(pattern)
            if ".git" not in p.parts and "ceo-android-app" not in p.parts
        ]
    assert materialized == [], materialized

    assert baseline["most_advanced_preserved_candidate"] == clean["candidate"]
    assert baseline["manifest_file_count"] == 45
    assert baseline["recovered_exact_source_count"] == 1
    assert baseline["unrecovered_source_body_count"] == 44
    assert baseline["preserved_identities"]["source_fingerprint"] == inputs["source_fingerprint"]
    assert baseline["preserved_identities"]["build_payload_sha256"] == inputs["build_payload_sha256"]
    assert baseline["preserved_identities"]["toolchain_lock_sha256"] == sha256(DEV21 / "TOOLCHAIN.lock.json")
    assert baseline["recovery_truth"]["full_original_android_source_recovered"] is False
    assert baseline["recovery_truth"]["metadata_and_contract_recovery_complete"] is True

    assert inventory["source_project_status"]["manifest_entries"] == 45
    assert inventory["source_project_status"]["exact_or_nested_source_files_recovered"] == 1
    assert inventory["source_project_status"]["real_gradle_project_materialized"] is False
    assert inventory["source_project_status"]["reconstruction_required"] is True

    assert lock["jdk"] == "17"
    assert lock["min_sdk"] == 26
    assert inputs["runtime_api35_executed"] is False
    assert inputs["runtime_api36_executed"] is False
    assert inputs["android_runtime_accepted"] is False
    assert inputs["production_verified"] is False

    assert master["only_active_project"] is True
    assert master["current_block"] == "M01"
    assert master["next_block"] == "M02"
    assert master["next_task"] == "APP007"
    assert master["physical_installation_allowed"] is False
    assert master["source_truth"]["expected_android_files"] == 45
    assert master["source_truth"]["exact_source_bodies_recovered"] == 1
    assert master["source_truth"]["source_bodies_to_reconstruct"] == 44

    checkpoint = (APP / "M01_MASTER_CHECKPOINT.md").read_text(encoding="utf-8")
    assert "M02 — Reconstrucción del proyecto Android real" in checkpoint
    assert "APP007" in checkpoint
    assert "CEO_ANDROID_FIRST_INSTALL_READY=true" in checkpoint

    print("M01_ANDROID_RECOVERY_QUALIFICATION_PASS")
    print("expected_files=45")
    print("recovered_source_bodies=1")
    print("reconstruct_in_M02=44")
    print("next=APP007")


if __name__ == "__main__":
    main()
