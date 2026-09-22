from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "ceo-android-app" / "android"


def must(path: str) -> Path:
    p = ANDROID / path
    assert p.is_file(), f"missing {path}"
    return p


def main() -> None:
    # APP007
    settings = must("settings.gradle.kts").read_text(encoding="utf-8")
    assert 'rootProject.name = "CEOAndroid"' in settings
    assert 'include(":app")' in settings
    assert "google()" in settings
    assert "mavenCentral()" in settings
    assert "gradlePluginPortal()" in settings

    # APP008
    root_build = must("build.gradle.kts").read_text(encoding="utf-8")
    props = must("gradle.properties").read_text(encoding="utf-8")
    assert 'id("com.android.application") version "9.2.1" apply false' in root_build
    assert 'id("org.jetbrains.kotlin.plugin.compose") version "2.3.21" apply false' in root_build
    assert "android.useAndroidX=true" in props
    assert "android.nonTransitiveRClass=true" in props

    # APP009
    app_build = must("app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'namespace = "ai.ceo.android"' in app_build
    assert 'applicationId = "ai.ceo.android.dev"' in app_build
    assert "compileSdk = 36" in app_build
    assert "minSdk = 26" in app_build
    assert "targetSdk = 36" in app_build
    assert "versionCode = 11" in app_build
    assert 'versionName = "0.9.0-dev-m02"' in app_build
    assert 'compose-bom:2026.04.01' in app_build
    assert "signingConfigs" not in app_build
    assert "storeFile" not in app_build

    # APP010
    manifest = must("app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android:name=".CEOApplication"' in manifest
    assert 'android:name=".MainActivity"' in manifest
    assert 'android.intent.action.MAIN' in manifest
    assert 'android.intent.category.LAUNCHER' in manifest
    assert 'android.permission.INTERNET' in manifest
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert 'android:allowBackup="false"' in manifest

    forbidden = [
        "REQUEST_INSTALL_PACKAGES",
        "MANAGE_EXTERNAL_STORAGE",
        "QUERY_ALL_PACKAGES",
        "SYSTEM_ALERT_WINDOW",
        "WRITE_SETTINGS",
        "BIND_ACCESSIBILITY_SERVICE",
    ]
    for permission in forbidden:
        assert permission not in manifest, permission

    policy = json.loads(must("REPOSITORY_POLICY.json").read_text(encoding="utf-8"))
    assert policy["project"] == "CEO App Android"
    assert policy["production"] is False
    assert policy["physical_phone_installation_allowed"] is False
    assert policy["payments"] is False
    assert policy["subscriptions"] is False
    assert policy["real_trading"] is False

    result = {
        "schema_version": 1,
        "status": "M02A_SOURCE_CONTRACT_PASS",
        "APP007": "PASS",
        "APP008": "PASS",
        "APP009": "PASS",
        "APP010": "PASS",
        "gradle_configuration_required": True,
        "kotlin_compile_required": False,
        "apk_build_required": False,
        "physical_installation_allowed": False,
    }
    out = ROOT / "ceo-android-app" / "M02A_SOURCE_VERIFICATION.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result))
    print("M02A_SOURCE_CONTRACT_PASS")


if __name__ == "__main__":
    main()
