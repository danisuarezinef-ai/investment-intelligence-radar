from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[2]
BASE = REPO / "ceo-updates" / "CEO_1.5.89-rc1-native-transport-integrity.zip"
SOURCE = REPO / "ceo-updates" / "mvp_field"
ROOT = pathlib.Path(os.environ.get("CEO_MVP_FIELD_BUILD_ROOT", "/tmp/ceo-mvp-field"))
OUT = REPO / "ceo-updates" / "mvp_field" / "CEO_MVP_FIELD_FIRST_REAL_GOAL.zip"


CMD = r"""@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
for %%P in (pythonw.exe python.exe pyw.exe py.exe) do (
  if not defined PY (
    where %%P >nul 2>nul
    if not errorlevel 1 set "PY=%%P"
  )
)

if not defined PY exit /b 7

if /I "%PY%"=="py.exe" (
  start "" /b py.exe -3 scripts\mvp_field_first_real_goal.py
) else if /I "%PY%"=="pyw.exe" (
  start "" /b pyw.exe -3 scripts\mvp_field_first_real_goal.py
) else (
  start "" /b "%PY%" scripts\mvp_field_first_real_goal.py
)
exit /b 0
"""


VBS = r"""Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = Chr(34) & base & "\ABRIR_MVP_FIELD.cmd" & Chr(34)
sh.Run "cmd.exe /c " & cmd, 0, False
"""


README = """CEO de IAs — MVP_FIELD / FIRST_REAL_GOAL

TEMPORARY FIELD BUNDLE. This is NOT an update and does NOT replace the installed CEO.

Double-click:
  MVP_FIELD_PRIMER_OBJETIVO.vbs

What runs:
- one fixed real goal (FIELD-MVP-01)
- one provider only: Gemini
- four normal steps; at most one correction + final verification
- one retry maximum per provider call
- no ContinuousScheduler
- no multi-provider router
- no recovery storm machinery
- no continuity audits
- no updater
- no self-development

Only success metric:
  delivery_pass = true

The final file, if successful, is:
  RESULTADOS_CEO\FIELD_MVP_01.md

Physical field execution is still required. Local/CI qualification cannot mark production ready.
"""


def main() -> None:
    if not BASE.is_file():
        raise RuntimeError(f"missing base package: {BASE}")
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)

    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    (ROOT / "ceo_core").mkdir(parents=True, exist_ok=True)
    (ROOT / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE / "first_real_goal_mode.py", ROOT / "ceo_core" / "mvp_field_first_real_goal.py")
    shutil.copy2(SOURCE / "launch_mvp_field.py", ROOT / "scripts" / "mvp_field_first_real_goal.py")
    (ROOT / "ABRIR_MVP_FIELD.cmd").write_text(CMD, encoding="utf-8", newline="\r\n")
    (ROOT / "MVP_FIELD_PRIMER_OBJETIVO.vbs").write_text(VBS, encoding="utf-8", newline="\r\n")
    (ROOT / "MVP_FIELD_README.txt").write_text(README, encoding="utf-8")

    # The normal app/update files remain byte-identical. MVP_FIELD is a parallel
    # entrypoint and never mutates the installed CEO or the stable update channel.
    OUT.unlink(missing_ok=True)
    fixed = (2026, 9, 21, 17, 45, 0)
    files = sorted(p for p in ROOT.rglob("*") if p.is_file())
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            rel = p.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(rel, date_time=fixed)
            info.create_system = 0
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0
            z.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    data = OUT.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    with zipfile.ZipFile(OUT) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError(f"bad zip member: {bad}")
        names = set(z.namelist())
    required = {
        "ceo_core/mvp_field_first_real_goal.py",
        "scripts/mvp_field_first_real_goal.py",
        "ABRIR_MVP_FIELD.cmd",
        "MVP_FIELD_PRIMER_OBJETIVO.vbs",
        "MVP_FIELD_README.txt",
    }
    missing = sorted(required - names)
    if missing:
        raise RuntimeError(f"missing MVP_FIELD files: {missing}")

    qualification = {
        "mode": "MVP_FIELD",
        "goal_id": "FIELD-MVP-01",
        "base_package": BASE.name,
        "artifact": OUT.name,
        "sha256": sha,
        "size_bytes": len(data),
        "entry_count": len(names),
        "normal_windows_app_modified": False,
        "stable_update_channel_modified": False,
        "continuous_scheduler_used": False,
        "multi_provider_used": False,
        "max_provider_retry_after_initial_attempt": 1,
        "normal_steps": 4,
        "maximum_steps_with_single_correction": 6,
        "success_metric": "delivery_pass",
        "physical_field_pending": True,
        "production_ready": False,
    }
    (SOURCE / "MVP_FIELD_QUALIFICATION.json").write_text(
        json.dumps(qualification, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(qualification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
