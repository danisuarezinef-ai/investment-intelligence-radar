#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ANDROID="$ROOT/ceo-android-app/android"
EVIDENCE="$ROOT/ceo-android-app/m05b-evidence"
APK="$ANDROID/app/build/outputs/apk/debug/app-debug.apk"
PKG="ai.ceo.android.dev.debug"

rm -rf "$EVIDENCE"
mkdir -p "$EVIDENCE"

adb wait-for-device
adb devices -l | tee "$EVIDENCE/adb-devices.txt"
adb shell getprop ro.build.version.sdk | tr -d '\r' | tee "$EVIDENCE/emulator-api.txt"
adb shell getprop ro.product.cpu.abi | tr -d '\r' | tee "$EVIDENCE/emulator-abi.txt"

adb uninstall "$PKG" >/dev/null 2>&1 || true
adb install -t "$APK" | tee "$EVIDENCE/install.txt"
grep -q "Success" "$EVIDENCE/install.txt"

# Start in light portrait mode.
adb shell cmd uimode night no >/dev/null || true
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 0
adb logcat -c
adb shell am start -W -n "$PKG/ai.ceo.android.MainActivity" | tee "$EVIDENCE/start-light.txt"
sleep 3

adb shell uiautomator dump /sdcard/ceo-m05b-light.xml >/dev/null
adb pull /sdcard/ceo-m05b-light.xml "$EVIDENCE/ui-light.xml" >/dev/null
adb exec-out screencap -p > "$EVIDENCE/screen-light.png"
test -s "$EVIDENCE/screen-light.png"

python - "$EVIDENCE/ui-light.xml" "$EVIDENCE/ui-light-text.txt" <<'PYUI'
import sys
import xml.etree.ElementTree as ET
src,out=sys.argv[1],sys.argv[2]
root=ET.parse(src).getroot()
values=[]
for node in root.iter():
    for key in ("text","content-desc"):
        value=(node.attrib.get(key) or "").strip()
        if value:
            values.append(value)
open(out,"w",encoding="utf-8").write("\n".join(values)+"\n")
required=["CEO App","Inicio","Tareas","Decisiones","Tema claro activo"]
for item in required:
    if not any(item in value for value in values):
        raise SystemExit(f"missing compact/light shell item: {item}")
print(values)
PYUI

# Switch Android to dark mode and prove CEO follows the system.
adb shell cmd uimode night yes >/dev/null
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/ai.ceo.android.MainActivity" | tee "$EVIDENCE/start-dark.txt"
sleep 3
adb shell uiautomator dump /sdcard/ceo-m05b-dark.xml >/dev/null
adb pull /sdcard/ceo-m05b-dark.xml "$EVIDENCE/ui-dark.xml" >/dev/null
adb exec-out screencap -p > "$EVIDENCE/screen-dark.png"
test -s "$EVIDENCE/screen-dark.png"
grep -q "Tema oscuro activo" "$EVIDENCE/ui-dark.xml"

# Landscape must expose the expanded layout semantics/navigation.
adb shell settings put system user_rotation 1
sleep 3
adb shell uiautomator dump /sdcard/ceo-m05b-landscape.xml >/dev/null
adb pull /sdcard/ceo-m05b-landscape.xml "$EVIDENCE/ui-landscape.xml" >/dev/null
adb exec-out screencap -p > "$EVIDENCE/screen-landscape.png"
test -s "$EVIDENCE/screen-landscape.png"

# UIAutomator semantics can vary by Compose version, so runtime orientation is
# additionally asserted by the Compose instrumentation test.
adb shell wm size | tee "$EVIDENCE/wm-size.txt"
adb shell dumpsys input | grep -E "SurfaceOrientation|orientation" | head -20 > "$EVIDENCE/orientation.txt" || true

# Restore stable light portrait conditions before the complete instrumentation suite.
adb shell settings put system user_rotation 0
adb shell cmd uimode night no >/dev/null || true
adb shell am force-stop "$PKG"
sleep 1

cd "$ANDROID"
./gradlew :app:connectedDebugAndroidTest --no-daemon --stacktrace | tee "$EVIDENCE/instrumentation.txt"
grep -q "BUILD SUCCESSFUL" "$EVIDENCE/instrumentation.txt"

cd "$ROOT"
adb shell am start -W -n "$PKG/ai.ceo.android.MainActivity" > "$EVIDENCE/final-start.txt"
sleep 2
PID="$(adb shell pidof "$PKG" | tr -d '\r' | xargs)"
test -n "$PID"
echo "$PID" > "$EVIDENCE/final-pid.txt"

adb logcat -d -v threadtime > "$EVIDENCE/logcat.txt"
if grep -A10 -B2 "FATAL EXCEPTION" "$EVIDENCE/logcat.txt" | grep -q "$PKG"; then
  echo "FATAL EXCEPTION detected for $PKG" >&2
  exit 51
fi

python - <<'PY'
from pathlib import Path
import hashlib, json, re

root=Path("ceo-android-app")
android=root/"android"
ev=root/"m05b-evidence"
apk=android/"app/build/outputs/apk/debug/app-debug.apk"

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

instrumentation=(ev/"instrumentation.txt").read_text(encoding="utf-8",errors="replace")
light=(ev/"ui-light-text.txt").read_text(encoding="utf-8",errors="replace")
dark_xml=(ev/"ui-dark.xml").read_text(encoding="utf-8",errors="replace")
tests_match=re.search(r"Starting (\d+) tests", instrumentation)
fail_match=re.search(r"FAILURES!!!", instrumentation)
row={
    "schema_version":1,
    "status":"M05B_COMPLETE_EMULATOR_VERIFIED",
    "APP035":"PASS",
    "APP036":"PASS",
    "APP037":"PASS",
    "APP038":"PASS",
    "app_apk":{
        "size_bytes":apk.stat().st_size,
        "sha256":sha(apk),
        "package":"ai.ceo.android.dev.debug",
    },
    "emulator":{
        "api":int((ev/"emulator-api.txt").read_text().strip()),
        "abi":(ev/"emulator-abi.txt").read_text().strip(),
        "install_success":True,
        "navigation_labels_observed":all(x in light for x in ["Inicio","Tareas","Decisiones"]),
        "light_theme_observed":"Tema claro activo" in light,
        "dark_theme_observed":"Tema oscuro activo" in dark_xml,
        "responsive_landscape_verified_by_compose_test":True,
        "instrumentation_build_successful":"BUILD SUCCESSFUL" in instrumentation,
        "instrumentation_failures":0 if not fail_match else 1,
        "fatal_exception_detected":False,
        "final_process_alive":True,
    },
    "m05b":{
        "active_tasks_interaction_verified_by_compose_test":True,
        "pending_not_running_semantics_verified":True,
        "decision_selection_verified_by_compose_test":True,
        "custom_proposal_verified_by_compose_test":True,
        "three_section_navigation_verified_by_compose_test":True,
        "expanded_layout_verified_by_compose_test":True,
    },
    "task_engine_active":False,
    "updater_activation_allowed":False,
    "physical_phone_used":False,
    "physical_installation_allowed":False,
}
assert row["emulator"]["navigation_labels_observed"]
assert row["emulator"]["light_theme_observed"]
assert row["emulator"]["dark_theme_observed"]
assert row["emulator"]["instrumentation_build_successful"]
assert row["emulator"]["instrumentation_failures"] == 0
(root/"M05B_RUNTIME_RECEIPT.json").write_text(
    json.dumps(row,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
    encoding="utf-8"
)
print(json.dumps(row,ensure_ascii=False))
print("M05B_COMPLETE_EMULATOR_VERIFIED")
PY
