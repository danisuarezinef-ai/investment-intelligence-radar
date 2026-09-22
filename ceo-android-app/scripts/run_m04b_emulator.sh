#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ANDROID="$ROOT/ceo-android-app/android"
EVIDENCE="$ROOT/ceo-android-app/m04b-evidence"
APK="$ANDROID/app/build/outputs/apk/debug/app-debug.apk"
TEST_APK="$ANDROID/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
PKG="ai.ceo.android.dev.debug"
TEST_PKG="ai.ceo.android.dev.debug.test"
ACTIVITY="ai.ceo.android.MainActivity"

mkdir -p "$EVIDENCE"
rm -f "$EVIDENCE"/*

adb wait-for-device
adb devices -l | tee "$EVIDENCE/adb-devices.txt"

API="$(adb shell getprop ro.build.version.sdk | tr -d '\r')"
ABI="$(adb shell getprop ro.product.cpu.abi | tr -d '\r')"
printf '%s\n' "$API" | tee "$EVIDENCE/emulator-api.txt"
printf '%s\n' "$ABI" | tee "$EVIDENCE/emulator-abi.txt"
test "$API" = "35"
test "$ABI" = "x86_64"

test -f "$APK"
test -f "$TEST_APK"

# APP027 — emulator-only installation.
adb uninstall "$TEST_PKG" >/dev/null 2>&1 || true
adb uninstall "$PKG" >/dev/null 2>&1 || true
adb install -t "$APK" | tee "$EVIDENCE/install-app.txt"
grep -q "Success" "$EVIDENCE/install-app.txt"

adb shell pm path "$PKG" | tee "$EVIDENCE/package-path.txt"
grep -q "^package:" "$EVIDENCE/package-path.txt"

adb shell dumpsys package "$PKG" > "$EVIDENCE/package-dumpsys.txt"
grep -q "versionCode=11" "$EVIDENCE/package-dumpsys.txt"
grep -q "versionName=0.9.0-dev-m02-debug" "$EVIDENCE/package-dumpsys.txt"

adb logcat -c

launch_cycle() {
  local cycle="$1"
  echo "=== M04-B launch cycle $cycle ==="

  adb shell am start -W -n "$PKG/$ACTIVITY" | tee "$EVIDENCE/start-$cycle.txt"
  grep -Eq "Status: ok|ThisTime:|TotalTime:" "$EVIDENCE/start-$cycle.txt"
  sleep 2

  local pid
  pid="$(adb shell pidof "$PKG" | tr -d '\r' | xargs)"
  test -n "$pid"
  printf '%s\n' "$pid" > "$EVIDENCE/pid-$cycle.txt"

  adb shell dumpsys activity activities > "$EVIDENCE/activity-$cycle.txt"
  grep -q "$ACTIVITY" "$EVIDENCE/activity-$cycle.txt"

  adb shell uiautomator dump /sdcard/ceo-m04b-ui.xml >/dev/null
  adb pull /sdcard/ceo-m04b-ui.xml "$EVIDENCE/ui-$cycle.xml" >/dev/null
  python - "$EVIDENCE/ui-$cycle.xml" "$EVIDENCE/ui-text-$cycle.txt" <<'PYUI'
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
print("UI_TEXTS:", values)
if not any("CEO App" in value for value in values):
    raise SystemExit("CEO App title not observable")
PYUI

  adb exec-out screencap -p > "$EVIDENCE/screen-$cycle.png"
  test -s "$EVIDENCE/screen-$cycle.png"

  adb shell am force-stop "$PKG"
  sleep 1
  if adb shell pidof "$PKG" | tr -d '\r' | grep -q '[0-9]'; then
    echo "CEO process still alive after force-stop on cycle $cycle" >&2
    exit 41
  fi
}

# APP028 — three complete stop/relaunch cycles.
launch_cycle 1
launch_cycle 2
launch_cycle 3

# Final live relaunch after the three stop cycles.
adb shell am start -W -n "$PKG/$ACTIVITY" | tee "$EVIDENCE/final-start.txt"
sleep 2
FINAL_PID="$(adb shell pidof "$PKG" | tr -d '\r' | xargs)"
test -n "$FINAL_PID"
printf '%s\n' "$FINAL_PID" > "$EVIDENCE/final-pid.txt"

# APP029 — reject CEO-owned fatal exceptions and ANRs.
adb logcat -d -v threadtime > "$EVIDENCE/logcat.txt"
python - "$EVIDENCE/logcat.txt" "$PKG" <<'PYLOG'
import sys
from pathlib import Path
path,pkg=sys.argv[1],sys.argv[2]
lines=Path(path).read_text(encoding="utf-8",errors="replace").splitlines()
problems=[]
for i,line in enumerate(lines):
    if "FATAL EXCEPTION" in line:
        block="\n".join(lines[max(0,i-3):min(len(lines),i+35)])
        if pkg in block or f"Process: {pkg}" in block:
            problems.append(block)
    if f"ANR in {pkg}" in line:
        problems.append("\n".join(lines[max(0,i-3):min(len(lines),i+20)]))
if problems:
    print("\n\n".join(problems))
    raise SystemExit("CEO fatal exception/ANR detected")
print("M04B_CRASH_SCAN_PASS")
PYLOG

# Install the instrumentation APK only inside the emulator and run it directly.
adb install -t -r "$TEST_APK" | tee "$EVIDENCE/install-test.txt"
grep -q "Success" "$EVIDENCE/install-test.txt"
adb shell am instrument -w "$TEST_PKG/androidx.test.runner.AndroidJUnitRunner"   | tee "$EVIDENCE/instrumentation.txt"
if grep -q "FAILURES!!!" "$EVIDENCE/instrumentation.txt"; then
  echo "Instrumentation reported failures" >&2
  exit 42
fi
python - "$EVIDENCE/instrumentation.txt" <<'PYINST'
import re,sys
from pathlib import Path
text=Path(sys.argv[1]).read_text(encoding="utf-8",errors="replace")
m=re.search(r"OK \((\d+) tests?\)", text)
if not m:
    raise SystemExit("JUnit success summary not found")
count=int(m.group(1))
if count < 3:
    raise SystemExit(f"Expected at least 3 instrumentation tests, got {count}")
print(f"M04B_INSTRUMENTATION_PASS tests={count}")
PYINST

# APP030 — persist runtime receipt.
cd "$ROOT"
python - <<'PY'
from pathlib import Path
import hashlib, json, re

root=Path("ceo-android-app")
ev=root/"m04b-evidence"
android=root/"android"
apk=android/"app/build/outputs/apk/debug/app-debug.apk"
test_apk=android/"app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

instrumentation=(ev/"instrumentation.txt").read_text(encoding="utf-8",errors="replace")
tests=None
m=re.search(r"OK \((\d+) tests?\)", instrumentation)
if m:
    tests=int(m.group(1))
else:
    # Shell gate already requires the JUnit success summary; this branch is defensive.
    tests=None

ui_observed=[]
for i in (1,2,3):
    values=(ev/f"ui-text-{i}.txt").read_text(encoding="utf-8",errors="replace").splitlines()
    ui_observed.append(values)

row={
    "schema_version":1,
    "status":"M04B_COMPLETE_EMULATOR_VERIFIED",
    "APP027":"PASS",
    "APP028":"PASS",
    "APP029":"PASS",
    "APP030":"PASS",
    "app_apk":{
        "size_bytes":apk.stat().st_size,
        "sha256":sha(apk),
        "package":"ai.ceo.android.dev.debug",
        "version_code":11,
        "version_name":"0.9.0-dev-m02-debug",
    },
    "instrumentation_apk":{
        "size_bytes":test_apk.stat().st_size,
        "sha256":sha(test_apk),
        "package":"ai.ceo.android.dev.debug.test",
    },
    "emulator":{
        "api":int((ev/"emulator-api.txt").read_text().strip()),
        "abi":(ev/"emulator-abi.txt").read_text().strip(),
        "install_success":True,
        "launch_cycles":3,
        "force_stop_relaunch_verified":True,
        "final_process_alive":bool((ev/"final-pid.txt").read_text().strip()),
        "fatal_exception_detected":False,
        "anr_detected":False,
        "instrumentation_pass":True,
        "instrumentation_test_count":tests,
        "ui_title_observed_each_cycle":all(
            any("CEO App" in value for value in values)
            for values in ui_observed
        ),
    },
    "evidence":{
        "screenshots":[f"m04b-evidence/screen-{i}.png" for i in (1,2,3)],
        "ui_hierarchies":[f"m04b-evidence/ui-{i}.xml" for i in (1,2,3)],
        "package_dump":"m04b-evidence/package-dumpsys.txt",
        "logcat":"m04b-evidence/logcat.txt",
        "instrumentation":"m04b-evidence/instrumentation.txt",
    },
    "physical_phone_used":False,
    "physical_installation_allowed":False,
    "production_verified":False,
    "updater_activation_allowed":False,
}
assert row["emulator"]["api"] == 35
assert row["emulator"]["abi"] == "x86_64"
assert row["emulator"]["ui_title_observed_each_cycle"] is True
(root/"M04B_RUNTIME_RECEIPT.json").write_text(
    json.dumps(row,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
    encoding="utf-8"
)
print(json.dumps(row,ensure_ascii=False))
print("M04B_COMPLETE_EMULATOR_VERIFIED")
PY
