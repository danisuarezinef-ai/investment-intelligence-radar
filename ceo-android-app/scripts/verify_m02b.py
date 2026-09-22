from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "ceo-android-app" / "android"


def must(rel: str) -> Path:
    p = ANDROID / rel
    assert p.is_file(), f"missing {rel}"
    return p


def text(rel: str) -> str:
    return must(rel).read_text(encoding="utf-8")


def main() -> None:
    # APP011 — Kotlin/Compose foundation.
    main = text("app/src/main/java/ai/ceo/android/MainActivity.kt")
    application = text("app/src/main/java/ai/ceo/android/CEOApplication.kt")
    prefs = text("app/src/main/java/ai/ceo/android/AppPreferences.kt")
    core = text("app/src/main/java/ai/ceo/android/AndroidCoreBridge.kt")
    updater_manager = text("app/src/main/java/ai/ceo/android/UpdateManager.kt")
    updater_policy = text("app/src/main/java/ai/ceo/android/UpdatePolicy.kt")
    verifier = text("app/src/main/java/ai/ceo/android/UpdateVerifier.kt")

    assert "class MainActivity : ComponentActivity()" in main
    assert "setContent" in main
    assert "@Composable" in main
    assert "CEOFoundationScreen" in main
    assert "OutlinedTextField" in main
    assert "Button" in main
    assert "class CEOApplication : Application()" in application
    assert "getSharedPreferences" in prefs
    assert "physicalInstallAllowed = false" in core
    assert "updaterActivationAllowed = false" in core
    assert "enabled = false" in updater_manager
    assert "INTERNAL_DOWNLOAD_ALLOWED = false" in updater_policy
    assert "INSTALL_HANDOFF_ALLOWED = false" in updater_policy
    assert "SILENT_INSTALL_ALLOWED = false" in updater_policy
    assert "MessageDigest.getInstance(\"SHA-256\")" in verifier

    # Kotlin sources required by the reconstructed foundation all exist.
    kotlin_main = sorted((ANDROID / "app/src/main/java/ai/ceo/android").glob("*.kt"))
    kotlin_debug = sorted((ANDROID / "app/src/debug/java/ai/ceo/android").glob("*.kt"))
    kotlin_tests = sorted((ANDROID / "app/src/androidTest/java/ai/ceo/android").glob("*.kt"))
    assert len(kotlin_main) >= 18
    assert len(kotlin_debug) >= 3
    assert len(kotlin_tests) >= 2

    # APP012 — resources are parseable and scoped.
    styles = must("app/src/main/res/values/styles.xml")
    update_paths = must("app/src/main/res/xml/update_file_paths.xml")
    ET.parse(styles)
    paths_root = ET.parse(update_paths).getroot()
    tags = [node.tag for node in paths_root]
    assert "files-path" in tags
    assert "cache-path" in tags
    fixture = text("app/src/debug/res/raw/golden_readonly_fixture.txt")
    assert "physical_installation_allowed=false" in fixture
    assert "internal_updater_activation=false" in fixture

    # APP013 — complete wrapper and pinned supported toolchain.
    wrapper = text("gradle/wrapper/gradle-wrapper.properties")
    jar = must("gradle/wrapper/gradle-wrapper.jar")
    gradlew = must("gradlew")
    gradlew_bat = must("gradlew.bat")
    assert "gradle-9.4.1-bin.zip" in wrapper
    assert jar.stat().st_size > 40_000
    assert gradlew.stat().st_size > 8_000
    assert gradlew_bat.stat().st_size > 2_000

    lock = json.loads(text("TOOLCHAIN.lock.json"))
    assert lock["jdk"] == "17"
    assert lock["gradle"] == "9.4.1"
    assert lock["android_gradle_plugin"] == "9.2.1"
    assert lock["compile_sdk"] == 36
    assert lock["target_sdk"] == 36
    assert lock["min_sdk"] == 26
    assert lock["build_tools"] == "36.0.0"
    assert lock["compose_bom"] == "2026.04.01"
    assert lock["m02_reconstructed_baseline"] is True

    # Python source is present but remains non-authoritative in M02.
    bridge = text("app/src/main/python/ceo_android_bridge.py")
    runtime = text("app/src/main/python/ceo_shared/runtime.py")
    assert "BLOCKED_UNTIL_M07" in bridge
    assert "shared_core_execution_enabled" in bridge
    assert "task_execution_enabled: bool = False" in runtime
    assert "physical_installation_allowed: bool = False" in runtime

    result = {
        "schema_version": 1,
        "status": "M02B_SOURCE_CONTRACT_PASS",
        "APP011": "SOURCE_PASS",
        "APP012": "SOURCE_PASS",
        "APP013": "SOURCE_PASS",
        "APP014": "BUILD_REQUIRED",
        "kotlin_main_files": len(kotlin_main),
        "kotlin_debug_files": len(kotlin_debug),
        "android_test_files": len(kotlin_tests),
        "resources_parseable": True,
        "gradle_wrapper_complete": True,
        "updater_activation_allowed": False,
        "physical_installation_allowed": False,
    }
    out = ROOT / "ceo-android-app" / "M02B_SOURCE_VERIFICATION.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    print("M02B_SOURCE_CONTRACT_PASS")


if __name__ == "__main__":
    main()
