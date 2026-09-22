from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "ceo-android-app"
ANDROID = APP / "android"


def load(path: Path) -> dict:
    row = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(row, dict), path
    return row


def main() -> None:
    split = load(APP / "M04_SPLIT_PLAN.json")
    a = load(APP / "M04A_QUALIFICATION.json")
    master = load(APP / "ANDROID_MASTER_STATE.json")

    assert split["current_focus"] == "M04-B"
    assert split["split"]["M04-A"]["status"] == "M04A_COMPLETE_CI_VERIFIED"
    assert split["split"]["M04-B"]["status"] == "PENDING_SEPARATE_ATTACK"
    assert split["physical_installation_allowed"] is False

    assert a["status"] == "M04A_COMPLETE_CI_VERIFIED"
    assert a["conclusion"] == "success"
    assert a["app_apk"]["package"] == "ai.ceo.android.dev.debug"
    assert a["app_apk"]["version_code"] == 11
    assert a["app_apk"]["min_sdk"] == 26
    assert a["app_apk"]["target_sdk"] == 36
    assert a["scope_limits"]["emulator_used"] is False
    assert a["scope_limits"]["physical_installation_allowed"] is False

    assert master["current_status"] == "M04A_COMPLETE_CI_VERIFIED"
    assert master["next_block"] == "M04-B"
    assert master["next_task"] == "APP027"
    assert master["physical_installation_allowed"] is False

    for rel in [
        "app/src/main/java/ai/ceo/android/MainActivity.kt",
        "app/src/androidTest/java/ai/ceo/android/InstallSmokeTest.kt",
        "app/src/androidTest/java/ai/ceo/android/AndroidStateSmokeTest.kt",
    ]:
        assert (ANDROID / rel).is_file(), rel

    main = (ANDROID / "app/src/main/java/ai/ceo/android/MainActivity.kt").read_text(encoding="utf-8")
    assert 'Text("CEO App"' in main
    assert "APP220" in main

    result = {
        "schema_version": 1,
        "status": "M04B_PRECHECK_PASS",
        "APP027": "EMULATOR_INSTALL_REQUIRED",
        "APP028": "RELAUNCH_REQUIRED",
        "APP029": "CRASH_FREE_AND_INSTRUMENTATION_REQUIRED",
        "APP030": "RUNTIME_EVIDENCE_REQUIRED",
        "expected_package": "ai.ceo.android.dev.debug",
        "emulator_api": 35,
        "emulator_abi": "x86_64",
        "physical_phone_used": False,
        "physical_installation_allowed": False,
    }
    (APP / "M04B_PRECHECK.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    print("M04B_PRECHECK_PASS")


if __name__ == "__main__":
    main()
