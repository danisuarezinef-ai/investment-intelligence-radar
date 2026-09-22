from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROOT = ROOT / "ceo-android-app"
ANDROID = APPROOT / "android"


def read(rel: str) -> str:
    p = ANDROID / rel
    assert p.is_file(), f"missing {rel}"
    return p.read_text(encoding="utf-8")


def main() -> None:
    gradle = read("app/build.gradle.kts")
    manifest = read("app/src/main/AndroidManifest.xml")
    debug_manifest = read("app/src/debug/AndroidManifest.xml")
    main = read("app/src/main/java/ai/ceo/android/MainActivity.kt")
    policy = json.loads(read("REPOSITORY_POLICY.json"))
    abi = json.loads(read("ANDROID_ABI_POLICY.json"))

    # APP023/024 prerequisites: clean debug build has a deterministic identity.
    assert 'applicationId = "ai.ceo.android.dev"' in gradle
    assert 'applicationIdSuffix = ".debug"' in gradle
    assert 'versionCode = 11' in gradle
    assert 'versionName = "0.9.0-dev-m02"' in gradle
    assert "compileSdk = 36" in gradle
    assert "targetSdk = 36" in gradle
    assert "minSdk = 26" in gradle

    # APP025/026 package and launcher structure.
    assert 'android:name=".CEOApplication"' in manifest
    assert 'android:name=".MainActivity"' in manifest
    assert 'android.intent.action.MAIN' in manifest
    assert 'android.intent.category.LAUNCHER' in manifest
    assert 'android:debuggable="true"' in debug_manifest

    # APP028/029 observable UI targets.
    assert 'Text("CEO App"' in main
    assert "APP220" in main

    # Instrumentation coverage exists before emulator execution.
    assert (ANDROID / "app/src/androidTest/java/ai/ceo/android/InstallSmokeTest.kt").is_file()
    assert (ANDROID / "app/src/androidTest/java/ai/ceo/android/AndroidStateSmokeTest.kt").is_file()

    # No phone install or updater activation is unlocked by M04.
    assert policy["physical_phone_installation_allowed"] is False
    assert abi["physical_installation_allowed"] is False

    result = {
        "schema_version": 1,
        "status": "M04_PRECHECK_PASS",
        "APP023": "BUILD_REQUIRED",
        "APP024": "APK_REQUIRED",
        "APP025": "APK_INSPECTION_REQUIRED",
        "APP026": "APK_IDENTITY_REQUIRED",
        "APP027": "EMULATOR_INSTALL_REQUIRED",
        "APP028": "EMULATOR_RELAUNCH_REQUIRED",
        "APP029": "CRASH_FREE_RUNTIME_REQUIRED",
        "APP030": "EVIDENCE_REQUIRED",
        "expected_package": "ai.ceo.android.dev.debug",
        "expected_version_code": 11,
        "expected_version_name": "0.9.0-dev-m02-debug",
        "emulator_api": 35,
        "emulator_abi": "x86_64",
        "physical_installation_allowed": False,
    }
    (APPROOT / "M04_PRECHECK.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result))
    print("M04_PRECHECK_PASS")


if __name__ == "__main__":
    main()
