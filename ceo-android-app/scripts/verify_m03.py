from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROOT = ROOT / "ceo-android-app"
ANDROID = APPROOT / "android"


def load(rel: str) -> dict:
    row = json.loads((ANDROID / rel).read_text(encoding="utf-8"))
    assert isinstance(row, dict), rel
    return row


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    lock = load("TOOLCHAIN.lock.json")
    env = load("BUILD_ENVIRONMENT.lock.json")
    abi = load("ANDROID_ABI_POLICY.json")
    sdk = load("ANDROID_SDK_PACKAGES.json")

    root_gradle = (ANDROID / "build.gradle.kts").read_text(encoding="utf-8")
    app_gradle = (ANDROID / "app/build.gradle.kts").read_text(encoding="utf-8")
    settings = (ANDROID / "settings.gradle.kts").read_text(encoding="utf-8")
    wrapper = (ANDROID / "gradle/wrapper/gradle-wrapper.properties").read_text(encoding="utf-8")
    props = (ANDROID / "gradle.properties").read_text(encoding="utf-8")

    # APP015 — JDK.
    assert lock["jdk"]["distribution"] == "temurin"
    assert lock["jdk"]["requested_version"] == "17.0.20"
    assert lock["jdk"]["verified_runtime_prefix"] == "17.0.20"
    assert lock["jdk"]["verified_vendor"] == "Eclipse Adoptium"

    # APP016 — Gradle wrapper and checksums.
    assert lock["gradle"]["version"] == "9.4.1"
    assert lock["gradle"]["distribution_sha256"] == "2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb"
    assert lock["gradle"]["wrapper_jar_sha256"] == "55243ef57851f12b070ad14f7f5bb8302daceeebc5bce5ece5fa6edb23e1145c"
    assert "gradle-9.4.1-bin.zip" in wrapper
    assert "distributionSha256Sum=2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb" in wrapper
    assert sha256(ANDROID / "gradle/wrapper/gradle-wrapper.jar") == lock["gradle"]["wrapper_jar_sha256"]

    # APP017 — AGP.
    assert lock["android"]["gradle_plugin"] == "9.2.1"
    assert 'id("com.android.application") version "9.2.1" apply false' in root_gradle

    # APP018 — Kotlin/Compose.
    kc = lock["kotlin_compose"]
    assert kc["plugin"] == "2.3.21"
    assert kc["compose_bom"] == "2026.04.01"
    assert kc["compose_core"] == "1.11.0"
    assert kc["activity_compose"] == "1.13.0"
    assert kc["androidx_core"] == "1.18.0"
    assert 'id("org.jetbrains.kotlin.plugin.compose") version "2.3.21" apply false' in root_gradle
    assert 'compose-bom:2026.04.01' in app_gradle
    assert 'androidx.activity:activity-compose:1.13.0' in app_gradle
    assert 'androidx.core:core-ktx:1.18.0' in app_gradle

    # APP019 — SDK / Build Tools.
    android = lock["android"]
    assert android["compile_sdk"] == 36
    assert android["target_sdk"] == 36
    assert android["min_sdk"] == 26
    assert android["build_tools"] == "36.0.0"
    assert sdk["compile_sdk"] == 36
    assert sdk["target_sdk"] == 36
    assert sdk["build_tools"] == "36.0.0"
    assert "compileSdk = 36" in app_gradle
    assert "targetSdk = 36" in app_gradle
    assert "minSdk = 26" in app_gradle

    # APP020 — ABI policy.
    assert abi["physical_device_primary_abi"] == "arm64-v8a"
    assert abi["ci_emulator_abi"] == "x86_64"
    assert abi["native_payload_present"] is False
    assert abi["physical_installation_allowed"] is False
    assert lock["abi"]["physical_device_primary"] == "arm64-v8a"
    assert lock["abi"]["ci_emulator"] == "x86_64"

    # APP021 — pinned CI environment and deterministic execution knobs.
    assert env["runner"] == "ubuntu-24.04"
    assert env["timezone"] == "UTC"
    assert env["locale"] == "C.UTF-8"
    assert env["source_date_epoch"] == 946684800
    assert env["github_actions"]["checkout"] == "11d5960a326750d5838078e36cf38b85af677262"
    assert env["github_actions"]["setup_java"] == "b6effb05e454b25005698d916606bdc6ffcbf961"
    assert env["github_actions"]["upload_artifact"] == "ea165f8d65b6e75b540449e92b4886f43607fa02"
    for required in [
        "org.gradle.daemon=false",
        "org.gradle.parallel=false",
        "org.gradle.workers.max=2",
        "org.gradle.vfs.watch=false",
        "kotlin.incremental=false",
        "kotlin.compiler.execution.strategy=in-process",
    ]:
        assert required in props

    # APP022 — active lock contains only what the M03 build actually uses.
    assert lock["policy"] == "active-build-dependencies-only"
    assert sorted(lock["removed_from_active_lock"]) == sorted(["chaquopy", "python_runtime", "androidx_work"])
    serialized = json.dumps(lock, sort_keys=True)
    assert '"chaquopy":' not in serialized
    assert '"python_runtime":' not in serialized
    assert '"androidx_work":' not in serialized

    # Reject dynamic/non-reproducible dependency declarations.
    build_text = "\n".join([root_gradle, app_gradle, settings])
    forbidden = [
        r'version\s+"latest',
        r':[+]["\']',
        r'-SNAPSHOT',
        r'mavenLocal\s*\(',
        r'\[[0-9].*,.*\)',
    ]
    for pattern in forbidden:
        assert not re.search(pattern, build_text, re.IGNORECASE), pattern

    result = {
        "schema_version": 1,
        "status": "M03_STATIC_TOOLCHAIN_PASS",
        "APP015": "PASS",
        "APP016": "PASS",
        "APP017": "PASS",
        "APP018": "PASS",
        "APP019": "PASS",
        "APP020": "PASS",
        "APP021": "DOUBLE_BUILD_REQUIRED",
        "APP022": "PASS",
        "physical_installation_allowed": False,
        "release_signing_required_for_this_gate": False,
        "reproducibility_target": "app-release-unsigned.apk",
    }
    (APPROOT / "M03_STATIC_VERIFICATION.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result))
    print("M03_STATIC_TOOLCHAIN_PASS")


if __name__ == "__main__":
    main()
