from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "ceo-android-app" / "android"


def must(rel: str) -> Path:
    p = ANDROID / rel
    assert p.is_file(), f"missing {rel}"
    return p


def main() -> None:
    gradle = must("app/build.gradle.kts").read_text(encoding="utf-8")
    manifest = must("app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    split = json.loads((ROOT / "ceo-android-app/M04_SPLIT_PLAN.json").read_text(encoding="utf-8"))

    assert split["current_focus"] == "M04-A"
    assert split["physical_installation_allowed"] is False

    # APP023/024 source preconditions.
    assert 'applicationId = "ai.ceo.android.dev"' in gradle
    assert 'applicationIdSuffix = ".debug"' in gradle
    assert 'versionCode = 11' in gradle
    assert 'versionName = "0.9.0-dev-m02"' in gradle
    assert 'versionNameSuffix = "-debug"' in gradle
    assert "minSdk = 26" in gradle
    assert "targetSdk = 36" in gradle
    assert "compileSdk = 36" in gradle
    assert 'testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"' in gradle
    assert 'androidTestImplementation("androidx.test:runner:1.7.0")' in gradle

    # APP025/026 manifest identity preconditions.
    assert 'android:name=".MainActivity"' in manifest
    assert 'android.intent.action.MAIN' in manifest
    assert 'android.intent.category.LAUNCHER' in manifest
    assert 'android:name=".CEOApplication"' in manifest
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert 'android:allowBackup="false"' in manifest

    result = {
        "schema_version": 1,
        "status": "M04A_SOURCE_PRECHECK_PASS",
        "APP023": "BUILD_REQUIRED",
        "APP024": "BUILD_REQUIRED",
        "APP025": "APK_INSPECTION_REQUIRED",
        "APP026": "APK_IDENTITY_REQUIRED",
        "emulator_required": False,
        "physical_installation_allowed": False,
    }
    out = ROOT / "ceo-android-app/M04A_PRECHECK.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result))
    print("M04A_SOURCE_PRECHECK_PASS")


if __name__ == "__main__":
    main()
