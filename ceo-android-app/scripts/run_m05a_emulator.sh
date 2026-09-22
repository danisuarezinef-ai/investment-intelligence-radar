#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ANDROID="$ROOT/ceo-android-app/android"
EVIDENCE="$ROOT/ceo-android-app/m05a-evidence"
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

adb logcat -c
adb shell am start -W -n "$PKG/ai.ceo.android.MainActivity" | tee "$EVIDENCE/start.txt"
sleep 3

PID="$(adb shell pidof "$PKG" | tr -d '\r' | xargs)"
test -n "$PID"
echo "$PID" > "$EVIDENCE/pid.txt"

adb shell dumpsys activity activities > "$EVIDENCE/activity.txt"
grep -q "ai.ceo.android.MainActivity" "$EVIDENCE/activity.txt"

adb shell uiautomator dump /sdcard/ceo-m05a-ui.xml >/dev/null
adb pull /sdcard/ceo-m05a-ui.xml "$EVIDENCE/ui.xml" >/dev/null
adb exec-out screencap -p > "$EVIDENCE/screen.png"
test -s "$EVIDENCE/screen.png"

python - "$EVIDENCE/ui.xml" "$EVIDENCE/ui-text.txt" <<'PYUI'
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
print(values)
required=["CEO App","Goal Engine","Mostrar objetivo"]
for item in required:
    if not any(item in value for value in values):
        raise SystemExit(f"missing observable shell text: {item}")
PYUI

cd "$ANDROID"
./gradlew :app:connectedDebugAndroidTest --no-daemon --stacktrace | tee "$EVIDENCE/instrumentation.txt"
grep -q "BUILD SUCCESSFUL" "$EVIDENCE/instrumentation.txt"

cd "$ROOT"
adb logcat -d -v threadtime > "$EVIDENCE/logcat.txt"
if grep -A10 -B2 "FATAL EXCEPTION" "$EVIDENCE/logcat.txt" | grep -q "$PKG"; then
  echo "FATAL EXCEPTION detected for $PKG" >&2
  exit 41
fi

python - <<'PY'
from pathlib import Path
import hashlib, json

root=Path("ceo-android-app")
android=root/"android"
ev=root/"m05a-evidence"
apk=android/"app/build/outputs/apk/debug/app-debug.apk"

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

instrumentation=(ev/"instrumentation.txt").read_text(encoding="utf-8",errors="replace")
ui=(ev/"ui-text.txt").read_text(encoding="utf-8",errors="replace")
row={
    "schema_version":1,
    "status":"M05A_COMPLETE_EMULATOR_VERIFIED",
    "APP031":"PASS",
    "APP032":"PASS",
    "APP033":"PASS",
    "APP034":"PASS",
    "app_apk":{
        "size_bytes":apk.stat().st_size,
        "sha256":sha(apk),
        "package":"ai.ceo.android.dev.debug",
    },
    "emulator":{
        "api":int((ev/"emulator-api.txt").read_text().strip()),
        "abi":(ev/"emulator-abi.txt").read_text().strip(),
        "install_success":True,
        "main_activity_visible":True,
        "goal_engine_observed":True,
        "goal_toggle_observed":True,
        "instrumentation_build_successful":"BUILD SUCCESSFUL" in instrumentation,
        "fatal_exception_detected":False,
    },
    "ui_shell":{
        "home":"CEO App" in ui,
        "goal_engine":"Goal Engine" in ui,
        "objective_collapsed_toggle":"Mostrar objetivo" in ui,
        "general_status_component_verified_by_compose_test":True,
        "progress_component_verified_by_compose_test":True,
        "interactive_goal_save_verified_by_compose_test":True,
    },
    "m05b_started":False,
    "physical_phone_used":False,
    "physical_installation_allowed":False,
}
(root/"M05A_RUNTIME_RECEIPT.json").write_text(
    json.dumps(row,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
    encoding="utf-8"
)
print(json.dumps(row,ensure_ascii=False))
print("M05A_COMPLETE_EMULATOR_VERIFIED")
PY
