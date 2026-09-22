from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROOT = ROOT / "ceo-android-app"
ANDROID = APPROOT / "android"
HIST = ROOT / "ceo-canonical" / "schemas" / "android_dev21"


def load(path: Path) -> dict:
    row = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(row, dict), path
    return row


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    old = load(HIST / "BUILD_PAYLOAD_MANIFEST.json")
    expected = {row["path"]: row for row in old["files"]}
    missing = [p for p in expected if not (ANDROID / p).is_file()]
    assert not missing, missing
    assert len(expected) == 45

    wrapper = [
        ANDROID / "gradlew",
        ANDROID / "gradlew.bat",
        ANDROID / "gradle/wrapper/gradle-wrapper.jar",
        ANDROID / "gradle/wrapper/gradle-wrapper.properties",
    ]
    assert all(p.is_file() for p in wrapper), wrapper

    exact_matches = []
    changed = []
    for rel, row in expected.items():
        actual = sha(ANDROID / rel)
        if actual == row["sha256"]:
            exact_matches.append(rel)
        else:
            changed.append(rel)
    assert len(changed) + len(exact_matches) == 45
    # M02 establishes a new buildable baseline. Historical hash equality is informative,
    # never required for reconstructed source bodies or the new supported toolchain.

    settings = (ANDROID / "settings.gradle.kts").read_text(encoding="utf-8")
    root_gradle = (ANDROID / "build.gradle.kts").read_text(encoding="utf-8")
    app_gradle = (ANDROID / "app/build.gradle.kts").read_text(encoding="utf-8")
    manifest = (ANDROID / "app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    main = (ANDROID / "app/src/main/java/ai/ceo/android/MainActivity.kt").read_text(encoding="utf-8")
    updater = (ANDROID / "app/src/main/java/ai/ceo/android/UpdatePolicy.kt").read_text(encoding="utf-8")
    pybridge = (ANDROID / "app/src/main/python/ceo_android_bridge.py").read_text(encoding="utf-8")

    assert 'include(":app")' in settings
    assert 'id("com.android.application") version "9.2.1"' in root_gradle
    assert 'id("org.jetbrains.kotlin.plugin.compose") version "2.3.21"' in root_gradle
    assert 'compileSdk = 36' in app_gradle
    assert 'targetSdk = 36' in app_gradle
    assert 'minSdk = 26' in app_gradle
    assert 'applicationId = "ai.ceo.android.dev"' in app_gradle
    assert 'versionCode = 11' in app_gradle
    assert 'versionName = "0.9.0-dev-m02"' in app_gradle
    assert 'android.permission.INTERNET' in manifest

    forbidden_permissions = (
        "REQUEST_INSTALL_PACKAGES",
        "MANAGE_EXTERNAL_STORAGE",
        "QUERY_ALL_PACKAGES",
        "SYSTEM_ALERT_WINDOW",
        "WRITE_SETTINGS",
    )
    assert not any(x in manifest for x in forbidden_permissions)

    assert "CEO App" in main
    assert "APP220" in main
    assert "INTERNAL_DOWNLOAD_ALLOWED = false" in updater
    assert "INSTALL_HANDOFF_ALLOWED = false" in updater
    assert "SILENT_INSTALL_ALLOWED = false" in updater
    assert "BLOCKED_UNTIL_M07" in pybridge
    assert "physical_installation_allowed" in pybridge

    lock = load(ANDROID / "TOOLCHAIN.lock.json")
    assert lock["jdk"] == "17"
    assert lock["gradle"] == "9.4.1"
    assert lock["android_gradle_plugin"] == "9.2.1"
    assert lock["compile_sdk"] == 36
    assert lock["target_sdk"] == 36
    assert lock["build_tools"] == "36.0.0"
    assert lock["m02_reconstructed_baseline"] is True
    assert lock["min_sdk"] == 26

    result = {
        "schema_version": 1,
        "status": "M02_SOURCE_STRUCTURE_VERIFIED",
        "expected_historical_paths": 45,
        "materialized_paths": 45,
        "historical_exact_hash_matches": sorted(exact_matches),
        "reconstructed_or_changed_paths": len(changed),
        "gradle_wrapper_complete": True,
        "compose_ui_present": True,
        "updater_scaffolding_present": True,
        "updater_activation_allowed": False,
        "physical_installation_allowed": False,
        "old_hash_equivalence_claimed": False,
    }
    out = APPROOT / "M02_SOURCE_VERIFICATION.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    print("M02_SOURCE_STRUCTURE_PASS")


if __name__ == "__main__":
    main()
